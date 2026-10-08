terraform {
  required_version = ">= 1.6, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "us-east-1"
}
variable "name" {
  type    = string
  default = "telecom-assurance-demo"
}
variable "vpc_id" {
  type        = string
  description = "Existing VPC with private connectivity for operators."
}
variable "private_subnet_ids" {
  type        = list(string)
  description = "Existing private subnets with NAT or ECR, S3, Logs and Secrets Manager endpoints."
  validation {
    condition     = length(var.private_subnet_ids) > 0
    error_message = "At least one private subnet is required."
  }
}
variable "client_security_group_id" {
  type        = string
  description = "Only this existing internal client/proxy security group may reach port 8000."
}
variable "api_key_secret_arn" {
  type        = string
  description = "Existing Secrets Manager secret holding the API key as plaintext; never pass its value."
}
variable "secret_kms_key_arn" {
  type        = string
  default     = null
  description = "Optional customer-managed KMS key for the API secret."
}
variable "image_digest" {
  type        = string
  description = "Digest of an image already pushed to this ECR repository before service deployment."
  validation {
    condition     = can(regex("^sha256:[a-f0-9]{64}$", var.image_digest))
    error_message = "Supply an immutable sha256 image digest."
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

resource "aws_ecr_repository" "app" {
  name                 = var.name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration {
    scan_on_push = true
  }
}
resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.name}"
  retention_in_days = 14
}
resource "aws_ecs_cluster" "app" {
  name = var.name
}

locals {
  task_trust = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        ArnLike      = { "aws:SourceArn" = "arn:${data.aws_partition.current.partition}:ecs:${var.region}:${data.aws_caller_identity.current.account_id}:*" }
      }
    }]
  })
}
resource "aws_iam_role" "execution" {
  name               = "${var.name}-execution"
  assume_role_policy = local.task_trust
}
resource "aws_iam_role" "task" {
  name               = "${var.name}-task"
  assume_role_policy = local.task_trust
  # No application AWS permissions: Bedrock is disabled and unsupported by this demo.
}
resource "aws_iam_role_policy" "execution" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      # ECR authorization does not support resource-level permissions.
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], Resource = aws_ecr_repository.app.arn },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.app.arn}:*" },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = var.api_key_secret_arn }
    ], var.secret_kms_key_arn == null ? [] : [
      { Effect = "Allow", Action = ["kms:Decrypt"], Resource = var.secret_kms_key_arn,
        Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.${var.region}.amazonaws.com" } } }
    ])
  })
}

resource "aws_security_group" "app" {
  name        = var.name
  description = "Private incident API; no database listeners"
  vpc_id      = var.vpc_id
}
resource "aws_vpc_security_group_ingress_rule" "api" {
  security_group_id            = aws_security_group.app.id
  referenced_security_group_id = var.client_security_group_id
  ip_protocol                 = "tcp"
  from_port                   = 8000
  to_port                     = 8000
}
resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.app.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "AWS API/image endpoints via existing NAT or private endpoints"
}
resource "aws_ecs_task_definition" "app" {
  family                   = var.name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name         = "app"
    image        = "${aws_ecr_repository.app.repository_url}@${var.image_digest}"
    essential    = true
    user         = "10001:10001"
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    secrets      = [{ name = "SERVICE_API_KEY", valueFrom = var.api_key_secret_arn }]
    environment = [
      { name = "INCIDENT_DB_PATH", value = "/app/data/runtime/incidents.db" },
      { name = "ACTION_AUDIT_PATH", value = "/app/data/runtime/action_audit.jsonl" }
    ]
    healthCheck = {
      command     = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "app"
      }
    }
  }])
}
resource "aws_ecs_service" "app" {
  name            = var.name
  cluster         = aws_ecs_cluster.app.id
  task_definition = aws_ecs_task_definition.app.arn
  launch_type     = "FARGATE"
  desired_count   = 1
  # Stop-before-start avoids two independent SQLite writers; it causes downtime.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }
  depends_on = [aws_iam_role_policy.execution]
}
resource "aws_appautoscaling_target" "app" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${aws_ecs_cluster.app.name}/${aws_ecs_service.app.name}"
  min_capacity       = 1
  max_capacity       = 1
}
resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.name}-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.app.service_namespace
  scalable_dimension = aws_appautoscaling_target.app.scalable_dimension
  resource_id        = aws_appautoscaling_target.app.resource_id
  target_tracking_scaling_policy_configuration {
    target_value = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    scale_in_cooldown  = 120
    scale_out_cooldown = 60
  }
}
output "repository_url" {
  value = aws_ecr_repository.app.repository_url
}
output "cluster_name" {
  value = aws_ecs_cluster.app.name
}
