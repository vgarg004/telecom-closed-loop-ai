# Private Fargate demonstration

This configuration is a reviewable deployment example, not a deployed service or a highly available production system. No resources were provisioned for this milestone.

Architecture: an existing internal client/proxy security group → private task ENI:8000 → one Fargate process → bundled CSV evidence + task-local SQLite/JSONL. ECR stores the image, Secrets Manager supplies an existing API key, and CloudWatch receives application logs. No public IP, public database, load balancer, NAT gateway or database is created. Operators reach the task's private IP through existing private connectivity; replacement changes that IP. Use an existing TLS proxy before sending credentials over a network.

Prerequisites:

- Terraform >=1.6, AWS provider 6.x, an authenticated deployment role and existing ECS/Application Auto Scaling service-linked roles (or authorization to create them).
- Existing VPC/private subnets, internal client security group, and NAT or endpoints for ECR API/DKR, S3, Logs and Secrets Manager. Endpoint policies/security groups must permit task HTTPS traffic. VPC DNS must be enabled.
- An existing Secrets Manager secret whose plaintext value is a strong API key. Supply only its ARN. For a customer-managed key, supply `secret_kms_key_arn` and permit the execution role in its key policy.
- A linux/amd64 image in the created ECR repository and its immutable digest. For initial bootstrap, an operator must create only the ECR repository first (`terraform apply -target=aws_ecr_repository.app`), publish the tested image, then plan the full configuration with its actual digest. For that ECR-only targeted bootstrap, supply a syntactically valid placeholder digest (`sha256:` followed by 64 zeros); replace it with the pushed image digest before any full plan/apply. Targeted apply is a bootstrap exception, not the routine deployment workflow. None of these provisioning/publishing steps were executed here.
- Protect local state/plan files or configure an encrypted remote backend with locking and restricted access before team use. Never commit state, variable secrets or plans.

Offline preparation (provider download needs network; no apply):

```bash
cd infra/terraform
terraform fmt -check
terraform init -backend=false
terraform validate
cp terraform.tfvars.example terraform.tfvars
# Edit IDs, region, secret ARN and image digest for your own account.
terraform plan -out=demo.tfplan
```

Review the plan and obtain deployment authorization separately. `plan` queries AWS; `init`/`validate` do not provision. The execution role can pull only this ECR repository, write only this log group, and retrieve only the configured secret. The one IAM wildcard is `ecr:GetAuthorizationToken`, which does not support repository-level restriction. The application task role has no AWS permissions; Bedrock is optional future integration, disabled by omission, with no model permission or credentials supplied. See [AWS execution role guidance](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html).

**SQLite restriction:** desired/minimum/maximum task counts are fixed at one. CPU target tracking is configured at 60% but cannot scale out while max capacity is one. Deployment percentages 0/100 enforce stop-before-start and cause downtime. There is no claim of distributed idempotency or durable ECS state: replacing/stopping the task loses incidents, approvals and JSONL audit files. Rolling back the image does not restore those files. Do not use this example for real remediation. Shared durable transactional state, durable audit storage, recovery semantics and concurrency testing must precede any replica increase. See [ECS deployment controls](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_service).

Cost-bearing resources: continuously running Fargate CPU/memory, ECR image storage/scanning where billed, CloudWatch ingestion/storage and autoscaling alarms. Existing Secrets Manager/KMS, NAT/endpoints, data transfer and private connectivity may add charges. Costs vary by region and usage; no cost estimate or free-tier claim is made.

Teardown, only after approval and backing up any needed demonstration state:

```bash
cd infra/terraform
terraform plan -destroy
terraform destroy
```

ECR deliberately has `force_delete=false`: remove its image versions separately after review before destroy can remove a nonempty repository. Destroy deletes this stack's log group as well. Existing VPC, subnets, client security group, secrets and networking remain because they are inputs, not managed resources. Check the account for remaining resources and costs afterward.
