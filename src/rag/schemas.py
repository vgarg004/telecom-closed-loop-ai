from typing import List
from pydantic import BaseModel, Field


class RAGAnswer(BaseModel):

    summary: str = Field(
        description="Short summary of the findings"
    )

    observations: List[str] = Field(
        description="Important observations supported by retrieved evidence"
    )

    possible_causes: List[str] = Field(
        description="Possible causes supported by retrieved evidence"
    )

    recommended_investigation: List[str] = Field(
        description="Recommended investigation steps"
    )