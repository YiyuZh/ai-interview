from typing import Any, Dict, Literal, Optional

from pydantic import Field

from ..base import BaseSchema


class InterviewStart(BaseSchema):
    resume_id: int
    target_position: str = "Python后端开发工程师"
    knowledge_base_id: Optional[int] = None
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    total_questions: int = Field(default=5, ge=3, le=10)
    multi_interviewer_enabled: bool = False


class InterviewStartResponse(BaseSchema):
    interview_id: int
    first_question: str
    question_index: int
    total_questions: int
    knowledge_base_title: Optional[str] = None
    interview_mode: str = "single"


class AnswerSubmit(BaseSchema):
    answer: str = Field(..., min_length=1, max_length=5000)


class AnswerResponse(BaseSchema):
    score: float
    feedback: str
    next_question: Optional[str] = None
    question_index: int
    is_finished: bool


class QuestionScore(BaseSchema):
    question: str
    score: float
    feedback: str


class InterviewReport(BaseSchema):
    interview_id: int
    overall_score: float
    total_questions: int
    report: Dict[str, Any]


class InterviewListItem(BaseSchema):
    interview_id: int
    target_position: str
    difficulty: str
    interview_mode: str = "single"
    overall_score: Optional[float] = None
    total_questions: int
    status: str
    created_at: Optional[str] = None
