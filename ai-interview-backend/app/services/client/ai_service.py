import json
import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError as OpenAIAuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
)

from app.core.config import settings
from app.exceptions.http_exceptions import ValidationError

logger = logging.getLogger(__name__)

PANEL_OUTPUT_VERSION = "panel_structured_v1"
PANEL_ROLE_ALIAS = {
    "technical_deep_dive": "technical",
    "project_follow_up": "project",
    "business_scenario": "business",
    "behavior_expression": "communication",
    "pressure_challenge": "pressure",
}
DEFAULT_PANEL_ROLES = [
    {
        "role_key": "technical_deep_dive",
        "role": "technical",
        "name": "Technical Deep Dive",
        "focus": "Probe core principles, engineering trade-offs, and technical depth.",
    },
    {
        "role_key": "project_follow_up",
        "role": "project",
        "name": "Project Follow-up",
        "focus": "Verify ownership, decisions, delivery quality, and retrospection.",
    },
    {
        "role_key": "business_scenario",
        "role": "business",
        "name": "Business Scenario",
        "focus": "Test business grounding, scenario reasoning, and practical trade-offs.",
    },
    {
        "role_key": "behavior_expression",
        "role": "communication",
        "name": "Behavior & Communication",
        "focus": "Observe structure, collaboration, clarity, and expression quality.",
    },
    {
        "role_key": "pressure_challenge",
        "role": "pressure",
        "name": "Pressure Challenge",
        "focus": "Test stress handling, risk awareness, and difficult trade-offs.",
    },
]


class AIService:
    @staticmethod
    def _resolve_runtime(ai_config: Optional[Dict] = None):
        if ai_config and ai_config.get("api_key"):
            provider = (ai_config.get("provider") or "deepseek").strip().lower()
            default_base_url = (
                settings.OPENAI_BASE_URL if provider == "openai" else settings.DEEPSEEK_BASE_URL
            )
            default_model = (
                settings.OPENAI_MODEL if provider == "openai" else settings.DEEPSEEK_MODEL
            )
            return (
                AsyncOpenAI(
                    api_key=ai_config["api_key"],
                    base_url=ai_config.get("base_url") or default_base_url,
                ),
                ai_config.get("model") or default_model,
                ai_config.get("source") or "user",
                ai_config.get("provider_label") or ("ChatGPT / OpenAI" if provider == "openai" else "DeepSeek"),
            )
        raise ValidationError(message="请先在个人中心保存可用的 AI API Key")

    @staticmethod
    def _translate_runtime_error(
        exc: Exception,
        source: str = "user",
        provider_label: str = "AI",
    ) -> ValidationError:
        if isinstance(exc, ValidationError):
            return exc
        if isinstance(exc, (OpenAIAuthenticationError, PermissionDeniedError)):
            return ValidationError(message=f"{provider_label} API Token 无效或已失效，请检查后重试")
        if isinstance(exc, RateLimitError):
            return ValidationError(message=f"{provider_label} API Token 额度不足或请求过于频繁，请检查后重试")
        if isinstance(exc, (APIConnectionError, APITimeoutError)):
            return ValidationError(message=f"连接 {provider_label} 失败，请检查网络或 Base URL 后重试")
        if isinstance(exc, BadRequestError):
            return ValidationError(message=f"{provider_label} 请求参数错误，请检查模型名或 Base URL 配置")
        if isinstance(exc, APIStatusError):
            status_code = getattr(exc, "status_code", None)
            if status_code in {401, 403}:
                return ValidationError(message=f"{provider_label} API Token 无效或已失效，请检查后重试")
            if status_code in {402, 429}:
                return ValidationError(message=f"{provider_label} API Token 额度不足或请求过于频繁，请检查后重试")
            if status_code in {502, 503, 504}:
                return ValidationError(message=f"连接 {provider_label} 失败，请稍后重试")
        return ValidationError(
            message=(
                f"调用你的 {provider_label} API 失败，请检查 API Token、Base URL 配置，"
                "或稍后再试"
            )
        )

    @staticmethod
    async def _chat(
        messages: list,
        temperature: float = 0.7,
        ai_config: Optional[Dict] = None,
    ) -> str:
        client, model, source, provider_label = AIService._resolve_runtime(ai_config)
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=2000,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.exception("AI provider chat call failed (%s): %s", source, exc)
            translated = AIService._translate_runtime_error(
                exc,
                source=source,
                provider_label=provider_label,
            )
            if translated is exc:
                raise
            raise translated from exc

    @staticmethod
    async def _chat_stream(
        messages: list,
        temperature: float = 0.7,
        ai_config: Optional[Dict] = None,
    ):
        client, model, source, provider_label = AIService._resolve_runtime(ai_config)
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=2000,
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as exc:
            logger.exception("AI provider stream call failed (%s): %s", source, exc)
            translated = AIService._translate_runtime_error(
                exc,
                source=source,
                provider_label=provider_label,
            )
            if translated is exc:
                raise
            raise translated from exc

    @staticmethod
    def _extract_json(text: str) -> Any:
        payload = (text or "").strip()
        if payload.startswith("```"):
            payload = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", payload)
            payload = re.sub(r"\s*```$", "", payload)
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", payload)
            if not match:
                raise
            return json.loads(match.group(1))

    @staticmethod
    def _normalize_panel_roles(panel_snapshot: Optional[Dict]) -> List[Dict]:
        raw_roles = (panel_snapshot or {}).get("roles") or []
        normalized = []
        for raw in raw_roles:
            role_key = raw.get("key") or raw.get("role_key") or raw.get("role")
            if not role_key:
                continue
            normalized.append(
                {
                    "role_key": role_key,
                    "role": PANEL_ROLE_ALIAS.get(role_key, role_key),
                    "name": raw.get("name") or role_key,
                    "focus": raw.get("focus") or raw.get("name") or role_key,
                }
            )
        return normalized or list(DEFAULT_PANEL_ROLES)

    @staticmethod
    def _string_or_empty(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _string_list(value: Any, limit: int = 6) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, Sequence):
            items = list(value)
        else:
            items = [value]
        normalized = []
        for item in items:
            text = AIService._string_or_empty(item)
            if text:
                normalized.append(text)
        return normalized[:limit]

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "y"}:
                return True
            if lowered in {"false", "0", "no", "n"}:
                return False
        return default

    @staticmethod
    def _collect_retrieved_slice_ids(
        knowledge_base: Optional[Dict] = None,
        question_plan: Optional[Sequence[Dict]] = None,
        question_meta: Optional[Dict] = None,
    ) -> List[int]:
        ordered_ids: List[int] = []

        def add_id(value: Any):
            try:
                slice_id = int(value)
            except (TypeError, ValueError):
                return
            if slice_id not in ordered_ids:
                ordered_ids.append(slice_id)

        for item in question_plan or []:
            for slice_item in item.get("selected_slices") or []:
                add_id(slice_item.get("slice_id"))

        for slice_item in (question_meta or {}).get("selected_slices") or []:
            add_id(slice_item.get("slice_id"))

        for slice_item in (knowledge_base or {}).get("slices") or []:
            add_id(slice_item.get("slice_id"))

        return ordered_ids

    @staticmethod
    def _build_panel_metadata(
        payload: Optional[Dict] = None,
        knowledge_base: Optional[Dict] = None,
        question_plan: Optional[Sequence[Dict]] = None,
        question_meta: Optional[Dict] = None,
    ) -> Dict:
        raw_metadata = (payload or {}).get("metadata") or {}
        return {
            "mode": raw_metadata.get("mode") or "panel",
            "version": raw_metadata.get("version") or PANEL_OUTPUT_VERSION,
            "retrieved_slice_ids": raw_metadata.get("retrieved_slice_ids")
            or AIService._collect_retrieved_slice_ids(
                knowledge_base=knowledge_base,
                question_plan=question_plan,
                question_meta=question_meta,
            ),
            "fallback_allowed": AIService._safe_bool(
                raw_metadata.get("fallback_allowed"),
                default=True,
            ),
        }

    @staticmethod
    def _build_panel_role_views(
        payload: Optional[Dict],
        panel_roles: Sequence[Dict],
        default_question_candidates: Optional[Sequence[str]] = None,
        default_followups: Optional[Sequence[str]] = None,
        default_evaluation_points: Optional[Sequence[str]] = None,
    ) -> List[Dict]:
        raw_items = []
        if isinstance(payload, dict):
            if isinstance(payload.get("panel"), list):
                raw_items = payload.get("panel") or []
            elif isinstance(payload.get("panel_views"), list):
                raw_items = payload.get("panel_views") or []

        role_map = {}
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            candidates = {
                raw.get("role"),
                raw.get("role_key"),
                PANEL_ROLE_ALIAS.get(raw.get("role"), raw.get("role")),
                PANEL_ROLE_ALIAS.get(raw.get("role_key"), raw.get("role_key")),
            }
            for candidate in candidates:
                if candidate:
                    role_map[str(candidate)] = raw

        normalized = []
        for role in panel_roles:
            raw = role_map.get(role["role_key"]) or role_map.get(role["role"]) or {}
            normalized.append(
                {
                    "role": role["role"],
                    "role_key": role["role_key"],
                    "focus": AIService._string_or_empty(raw.get("focus")) or role["focus"],
                    "question_candidates": AIService._string_list(
                        raw.get("question_candidates") or default_question_candidates
                    ),
                    "followup_candidates": AIService._string_list(
                        raw.get("followup_candidates") or default_followups
                    ),
                    "evaluation_points": AIService._string_list(
                        raw.get("evaluation_points") or default_evaluation_points
                    ),
                }
            )
        return normalized

    @staticmethod
    def _normalize_panel_question_payload(
        payload: Dict,
        question_plan: Sequence[Dict],
        knowledge_base: Optional[Dict] = None,
        panel_snapshot: Optional[Dict] = None,
    ) -> Dict:
        if not isinstance(payload, dict):
            raise ValueError("Panel payload is not an object")

        panel_roles = AIService._normalize_panel_roles(panel_snapshot)
        raw_moderator = payload.get("moderator") or {}
        raw_decisions = raw_moderator.get("selected_questions")
        if not isinstance(raw_decisions, list):
            raw_decisions = payload.get("questions") or []
        if not isinstance(raw_decisions, list):
            raise ValueError("Panel selected questions payload is not a list")

        base_panel = AIService._build_panel_role_views(
            payload=payload,
            panel_roles=panel_roles,
        )
        moderator_feedback_style = (
            AIService._string_or_empty(raw_moderator.get("feedback_style"))
            or AIService._string_or_empty(payload.get("moderator_style"))
        )
        moderator_difficulty_hint = AIService._string_or_empty(raw_moderator.get("difficulty_hint"))
        moderator_summary = AIService._string_or_empty(raw_moderator.get("reasoning_summary"))
        metadata = AIService._build_panel_metadata(
            payload=payload,
            knowledge_base=knowledge_base,
            question_plan=question_plan,
        )

        questions = []
        moderator_questions = []
        for index, plan in enumerate(question_plan):
            raw = raw_decisions[index] if index < len(raw_decisions) else {}
            if isinstance(raw, str):
                raw = {"selected_question": raw}
            if not isinstance(raw, dict):
                raise ValueError(f"Panel question decision #{index} is invalid")

            question_text = AIService._string_or_empty(
                raw.get("selected_question") or raw.get("question")
            )
            if not question_text:
                raise ValueError(f"Panel question decision #{index} is missing selected_question")

            selected_followups = AIService._string_list(
                raw.get("selected_followups") or raw.get("followup_candidates")
            )
            evaluation_points = AIService._string_list(
                raw.get("evaluation_points") or plan.get("evaluation_focus")
            )
            reasoning_summary = AIService._string_or_empty(
                raw.get("reasoning_summary")
                or raw.get("panel_reasoning_summary")
                or moderator_summary
            )
            used_slice_ids = raw.get("used_slice_ids") or raw.get("retrieved_slice_ids") or [
                item.get("slice_id") for item in (plan.get("selected_slices") or []) if item.get("slice_id")
            ]

            panel_views = AIService._build_panel_role_views(
                payload=payload,
                panel_roles=panel_roles,
                default_question_candidates=[question_text],
                default_followups=selected_followups,
                default_evaluation_points=evaluation_points,
            )
            panel_context = {
                "panel": panel_views,
                "moderator": {
                    "selected_question": question_text,
                    "selected_followups": selected_followups,
                    "reasoning_summary": reasoning_summary,
                    "feedback_style": moderator_feedback_style,
                    "difficulty_hint": AIService._string_or_empty(
                        raw.get("difficulty_hint") or moderator_difficulty_hint
                    ),
                },
                "metadata": {
                    **metadata,
                    "retrieved_slice_ids": used_slice_ids or metadata["retrieved_slice_ids"],
                },
            }

            question_item = {
                "index": index,
                "question": question_text,
                "category": raw.get("category") or plan.get("category"),
                "stage": raw.get("stage") or plan.get("stage"),
                "lead_role": raw.get("lead_role") or plan.get("lead_role"),
                "support_roles": raw.get("support_roles") or plan.get("support_roles") or [],
                "intent": raw.get("intent") or plan.get("intent"),
                "evaluation_focus": evaluation_points or plan.get("evaluation_focus") or [],
                "used_slice_ids": used_slice_ids or [],
                "selected_followups": selected_followups,
                "panel_reasoning_summary": reasoning_summary,
                "difficulty_hint": panel_context["moderator"]["difficulty_hint"],
                "panel_context": panel_context,
            }
            questions.append(question_item)
            moderator_questions.append(
                {
                    "index": index,
                    "selected_question": question_text,
                    "selected_followups": selected_followups,
                    "reasoning_summary": reasoning_summary,
                    "difficulty_hint": panel_context["moderator"]["difficulty_hint"],
                    "used_slice_ids": used_slice_ids or [],
                }
            )

        return {
            "panel": base_panel,
            "moderator": {
                "selected_questions": moderator_questions,
                "reasoning_summary": moderator_summary,
                "feedback_style": moderator_feedback_style,
                "difficulty_hint": moderator_difficulty_hint,
            },
            "metadata": metadata,
            "questions": questions,
            "moderator_style": moderator_feedback_style,
        }

    @staticmethod
    def _normalize_panel_evaluation_payload(
        payload: Dict,
        question_meta: Optional[Dict] = None,
        knowledge_base: Optional[Dict] = None,
        panel_snapshot: Optional[Dict] = None,
    ) -> Dict:
        if not isinstance(payload, dict):
            raise ValueError("Panel evaluation payload is not an object")

        panel_roles = AIService._normalize_panel_roles(panel_snapshot)
        raw_moderator = payload.get("moderator") or {}
        moderator_feedback = AIService._string_or_empty(
            raw_moderator.get("feedback") or payload.get("feedback")
        )
        if not moderator_feedback:
            raise ValueError("Panel evaluation payload is missing feedback")

        metadata = AIService._build_panel_metadata(
            payload=payload,
            knowledge_base=knowledge_base,
            question_meta=question_meta,
        )
        selected_followups = AIService._string_list(
            raw_moderator.get("selected_followups")
            or payload.get("selected_followups")
            or (question_meta or {}).get("selected_followups")
        )
        evaluation_points = AIService._string_list(
            payload.get("evaluation_points")
            or raw_moderator.get("evaluation_points")
            or (question_meta or {}).get("evaluation_focus")
        )
        reasoning_summary = AIService._string_or_empty(raw_moderator.get("reasoning_summary"))
        panel = AIService._build_panel_role_views(
            payload=payload,
            panel_roles=panel_roles,
            default_question_candidates=[(question_meta or {}).get("question")] if (question_meta or {}).get("question") else [],
            default_followups=selected_followups,
            default_evaluation_points=evaluation_points,
        )

        score = AIService._safe_float(raw_moderator.get("score") or payload.get("score"), default=5.0)
        moderator = {
            "selected_question": AIService._string_or_empty((question_meta or {}).get("question")),
            "selected_followups": selected_followups,
            "reasoning_summary": reasoning_summary,
            "feedback_style": AIService._string_or_empty(raw_moderator.get("feedback_style")),
            "difficulty_hint": AIService._string_or_empty(
                raw_moderator.get("difficulty_hint") or (question_meta or {}).get("difficulty_hint")
            ),
            "score": score,
            "feedback": moderator_feedback,
            "follow_up": AIService._safe_bool(
                raw_moderator.get("follow_up") if "follow_up" in raw_moderator else payload.get("follow_up"),
                default=False,
            ),
            "next_focus": AIService._string_or_empty(
                raw_moderator.get("next_focus") or payload.get("next_focus")
            ),
        }

        return {
            "score": score,
            "feedback": moderator_feedback,
            "follow_up": moderator["follow_up"],
            "strengths": AIService._string_list(payload.get("strengths")),
            "gaps": AIService._string_list(payload.get("gaps")),
            "next_focus": moderator["next_focus"],
            "panel_views": [
                {
                    "role": item["role_key"],
                    "summary": "; ".join(item["evaluation_points"] or item["followup_candidates"] or [item["focus"]]),
                }
                for item in panel
            ],
            "panel": panel,
            "moderator": moderator,
            "metadata": metadata,
        }

    @staticmethod
    def _trim_text(value: Optional[str], limit: int) -> str:
        text = (value or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

    @staticmethod
    def _resume_snapshot(parsed_resume: dict) -> str:
        compact = {
            "name": parsed_resume.get("name"),
            "education": parsed_resume.get("education"),
            "skills": parsed_resume.get("skills", [])[:12],
            "experience": parsed_resume.get("experience", [])[:4],
            "projects": parsed_resume.get("projects", [])[:4],
            "summary": parsed_resume.get("summary"),
        }
        return json.dumps(compact, ensure_ascii=False)

    @staticmethod
    def _history_text(chat_history: Sequence[Dict], limit: int = 6) -> str:
        lines = []
        for item in list(chat_history or [])[-limit:]:
            role = "Interviewer" if item.get("role") == "interviewer" else "Candidate"
            lines.append(f"{role}: {item.get('content', '')}")
        return "\n".join(lines)

    @staticmethod
    def _slice_line(item: Dict, limit: int = 220) -> str:
        stage = "/".join((item.get("stage_tags") or [])[:2]) or "-"
        role = "/".join((item.get("role_tags") or [])[:2]) or "-"
        scene = "/".join((item.get("scene_tags") or [])[:2]) or "-"
        return (
            f"[slice#{item.get('slice_id', '?')}] "
            f"[{item.get('source_section') or item.get('slice_type') or 'knowledge'}] "
            f"[stage={stage}] [role={role}] [scene={scene}] "
            f"{AIService._trim_text(item.get('content'), limit)}"
        )

    @staticmethod
    def _build_knowledge_base_context(
        knowledge_base: Optional[dict],
        selected_slices: Optional[Sequence[Dict]] = None,
        max_slices: int = 4,
    ) -> str:
        if not knowledge_base:
            return "No knowledge base selected. Rely on resume and target position only."

        lines = [
            "Knowledge base context is available. Use it to calibrate interview focus, but do not copy it verbatim.",
            f"Knowledge base title: {knowledge_base.get('title') or 'Untitled'}",
            f"Target position: {knowledge_base.get('target_position') or '-'}",
            f"Source scope: {knowledge_base.get('scope') or 'private'}",
        ]

        slices = list(selected_slices or [])
        if not slices:
            slices = list((knowledge_base.get("slices") or [])[:max_slices])

        if slices:
            lines.append("Top routed knowledge slices:")
            for item in slices[:max_slices]:
                lines.append(f"- {AIService._slice_line(item)}")
            return "\n".join(lines)

        knowledge_content = AIService._trim_text(knowledge_base.get("knowledge_content"), 2200)
        focus_points = AIService._trim_text(knowledge_base.get("focus_points"), 1200)
        interviewer_prompt = AIService._trim_text(knowledge_base.get("interviewer_prompt"), 1200)
        if knowledge_content:
            lines.append(f"Knowledge content: {knowledge_content}")
        if focus_points:
            lines.append(f"Focus points: {focus_points}")
        if interviewer_prompt:
            lines.append(f"Interviewer guidance: {interviewer_prompt}")
        return "\n".join(lines)

    @staticmethod
    def _build_question_plan_context(question_plan: Optional[Sequence[Dict]]) -> str:
        if not question_plan:
            return ""
        lines = ["Question plan and routed slices:"]
        for item in question_plan:
            lines.append(
                f"- Plan #{item.get('index', 0)}: "
                f"stage={item.get('stage')}, category={item.get('category')}, "
                f"lead_role={item.get('lead_role')}, support_roles={','.join(item.get('support_roles') or []) or '-'}"
            )
            lines.append(f"  intent: {item.get('intent')}")
            evaluation_focus = item.get("evaluation_focus") or []
            if evaluation_focus:
                lines.append(f"  evaluation_focus: {', '.join(evaluation_focus)}")
            for slice_item in (item.get("selected_slices") or [])[:3]:
                lines.append(f"  routed_slice: {AIService._slice_line(slice_item, limit=180)}")
        return "\n".join(lines)

    @staticmethod
    def _build_panel_context(panel_snapshot: Optional[Dict]) -> str:
        if not panel_snapshot or panel_snapshot.get("mode") != "panel":
            return "Single interviewer mode."
        lines = [
            "Internal panel mode is enabled.",
            f"Moderator name: {panel_snapshot.get('moderator_name') or '主持人'}",
            "Internal roles:",
        ]
        for role in panel_snapshot.get("roles") or []:
            lines.append(
                f"- {role.get('key')}: {role.get('name')} | focus={role.get('focus')}"
            )
        return "\n".join(lines)

    @staticmethod
    def _build_report_signal_context(report_signals: Optional[Dict]) -> str:
        if not report_signals:
            return ""
        lines = ["Aggregated interview signals:"]
        if report_signals.get("common_gaps"):
            lines.append(f"- Common gaps: {', '.join(report_signals.get('common_gaps') or [])}")
        if report_signals.get("common_strengths"):
            lines.append(f"- Common strengths: {', '.join(report_signals.get('common_strengths') or [])}")
        if report_signals.get("training_priorities"):
            lines.append(
                f"- Training priorities: {', '.join(report_signals.get('training_priorities') or [])}"
            )
        if report_signals.get("retrieved_slice_ids"):
            lines.append(
                f"- Retrieved slice ids: {', '.join(str(item) for item in report_signals.get('retrieved_slice_ids') or [])}"
            )
        if report_signals.get("panel_summary"):
            lines.append("Panel summaries:")
            for item in report_signals.get("panel_summary") or []:
                if isinstance(item, dict):
                    lines.append(
                        f"- {item.get('role')}: {item.get('summary') or item.get('title') or ''}"
                    )
        return "\n".join(lines)

    @staticmethod
    def _normalize_question_array(payload: Any) -> List[Dict]:
        if isinstance(payload, dict) and isinstance(payload.get("questions"), list):
            payload = payload["questions"]
        if not isinstance(payload, list):
            raise ValueError("Question payload is not a list")

        normalized = []
        for index, item in enumerate(payload):
            if isinstance(item, str):
                normalized.append({"index": index, "question": item, "category": "technical"})
                continue
            if isinstance(item, dict):
                normalized.append(item)
        if not normalized:
            raise ValueError("Question payload is empty")
        return normalized

    @staticmethod
    async def parse_resume(resume_text: str, ai_config: Optional[Dict] = None) -> dict:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert resume parser. Return pure JSON only. "
                    "Extract: name, education, skills, experience, projects, summary. "
                    "Keep skills/experience/projects as arrays. Reply in Simplified Chinese when text needs summarization."
                ),
            },
            {
                "role": "user",
                "content": f"Resume text:\n{resume_text}",
            },
        ]
        result = await AIService._chat(messages, temperature=0.2, ai_config=ai_config)
        return AIService._extract_json(result)

    @staticmethod
    async def analyze_resume(
        parsed_resume: dict,
        target_position: str,
        ai_config: Optional[Dict] = None,
    ) -> dict:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior recruiter and interview coach. "
                    "Analyze the resume for the target role and return pure JSON only. "
                    "Schema: "
                    '{"overall_score":7.5,"strengths":[""],"weaknesses":[""],'
                    '"suggestions":[""],"keyword_match":[""],"missing_keywords":[""],"summary":""}. '
                    "Reply in Simplified Chinese."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Target position: {target_position}\n"
                    f"Parsed resume JSON: {json.dumps(parsed_resume, ensure_ascii=False)}"
                ),
            },
        ]
        result = await AIService._chat(messages, temperature=0.4, ai_config=ai_config)
        return AIService._extract_json(result)

    @staticmethod
    async def generate_questions(
        parsed_resume: dict,
        target_position: str,
        difficulty: str,
        count: int,
        knowledge_base: Optional[dict] = None,
        question_plan: Optional[Sequence[Dict]] = None,
        ai_config: Optional[Dict] = None,
    ) -> list:
        difficulty_desc = {
            "easy": "junior-friendly, focus on fundamentals and clear project narration",
            "medium": "balanced, cover project depth and practical engineering decisions",
            "hard": "senior-level, include architecture trade-offs, performance and risk handling",
        }.get(difficulty, "balanced")
        knowledge_context = AIService._build_knowledge_base_context(knowledge_base)
        plan_context = AIService._build_question_plan_context(question_plan)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior interviewer designing a realistic mock interview. "
                    "Reply in Simplified Chinese. "
                    f"Target role: {target_position}. Difficulty: {difficulty_desc}. "
                    f"Generate exactly {count} interview questions. "
                    "The first question must be self-introduction. "
                    "If question plan is provided, strictly follow the stage/category/intent order. "
                    "Use the routed knowledge slices as the primary calibration source. "
                    "Return pure JSON array only with schema: "
                    '[{"index":0,"question":"...","category":"self-intro|project|technical|system-design|behavior"}].\n'
                    f"{knowledge_context}\n{plan_context}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Candidate resume JSON: {AIService._resume_snapshot(parsed_resume)}\n"
                    f"Target position: {target_position}"
                ),
            },
        ]
        result = await AIService._chat(messages, temperature=0.65, ai_config=ai_config)
        return AIService._normalize_question_array(AIService._extract_json(result))

    @staticmethod
    async def generate_panel_questions(
        parsed_resume: dict,
        target_position: str,
        difficulty: str,
        count: int,
        question_plan: Sequence[Dict],
        knowledge_base: Optional[dict] = None,
        panel_snapshot: Optional[Dict] = None,
        ai_config: Optional[Dict] = None,
    ) -> dict:
        difficulty_desc = {
            "easy": "keep the bar realistic and training-oriented",
            "medium": "balance challenge and coaching value",
            "hard": "challenge the candidate with depth and pressure, but stay fair",
        }.get(difficulty, "balance challenge and coaching value")
        messages = [
            {
                "role": "system",
                "content": (
                    "You are simulating one internal interview panel with multiple roles, but only one moderator speaks outwardly. "
                    "Use a single model call and return strict JSON only. "
                    "Do not output chain-of-thought. Keep reasoning summaries brief. "
                    "Every panel role must think from its own focus, propose candidates, then the moderator selects the final question. "
                    "Return an object with this schema: "
                    '{"panel":[{"role":"technical","role_key":"technical_deep_dive","focus":"",'
                    '"question_candidates":[""],"followup_candidates":[""],"evaluation_points":[""]}],'
                    '"moderator":{"selected_questions":[{"index":0,"selected_question":"",'
                    '"selected_followups":[""],"reasoning_summary":"",'
                    '"lead_role":"technical_deep_dive","support_roles":["project_follow_up"],'
                    '"evaluation_points":[""],"used_slice_ids":[1,2]}],'
                    '"reasoning_summary":"","feedback_style":"","difficulty_hint":""},'
                    '"metadata":{"mode":"panel","version":"panel_structured_v1",'
                    '"retrieved_slice_ids":[1,2],"fallback_allowed":true}}. '
                    f"Generate exactly {count} selected questions. "
                    f"Target role: {target_position}. Difficulty guidance: {difficulty_desc}. "
                    "If routed slices exist, prefer them and reference the used slice ids in moderator.selected_questions[].used_slice_ids.\n"
                    f"{AIService._build_panel_context(panel_snapshot)}\n"
                    f"{AIService._build_knowledge_base_context(knowledge_base)}\n"
                    f"{AIService._build_question_plan_context(question_plan)}"
                ),
            },
            {
                "role": "user",
                "content": f"Candidate resume JSON: {AIService._resume_snapshot(parsed_resume)}",
            },
        ]
        result = await AIService._chat(messages, temperature=0.5, ai_config=ai_config)
        payload = AIService._extract_json(result)
        normalized = AIService._normalize_panel_question_payload(
            payload=payload,
            question_plan=question_plan,
            knowledge_base=knowledge_base,
            panel_snapshot=panel_snapshot,
        )
        logger.info(
            "Panel structured question generation succeeded: roles=%s questions=%s",
            len(normalized.get("panel") or []),
            len(normalized.get("questions") or []),
        )
        return normalized

    @staticmethod
    async def evaluate_answer(
        question: str,
        answer: str,
        resume_context: dict,
        chat_history: list,
        next_question: Optional[str] = None,
        knowledge_base: Optional[dict] = None,
        question_meta: Optional[Dict] = None,
        ai_config: Optional[Dict] = None,
    ) -> dict:
        selected_slices = (question_meta or {}).get("selected_slices") or None
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior interviewer and interview coach. "
                    "Evaluate the candidate answer and return pure JSON only. "
                    "Reply in Simplified Chinese. "
                    'Schema: {"score":7.5,"feedback":"","follow_up":false,"strengths":[""],"gaps":[""]}. '
                    "Score range is 1-10. Feedback should be concise and actionable."
                    f"\n{AIService._build_knowledge_base_context(knowledge_base, selected_slices=selected_slices)}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Resume JSON: {AIService._resume_snapshot(resume_context)}\n"
                    f"Chat history:\n{AIService._history_text(chat_history)}\n"
                    f"Question: {question}\n"
                    f"Candidate answer: {answer}\n"
                    f"Question intent: {(question_meta or {}).get('intent') or '-'}\n"
                    f"Evaluation focus: {', '.join((question_meta or {}).get('evaluation_focus') or []) or '-'}\n"
                    f"Next question: {next_question or '-'}"
                ),
            },
        ]
        result = await AIService._chat(messages, temperature=0.35, ai_config=ai_config)
        return AIService._extract_json(result)

    @staticmethod
    async def evaluate_answer_with_panel(
        question: str,
        answer: str,
        resume_context: dict,
        chat_history: list,
        knowledge_base: Optional[dict] = None,
        question_meta: Optional[Dict] = None,
        panel_snapshot: Optional[Dict] = None,
        ai_config: Optional[Dict] = None,
    ) -> dict:
        selected_slices = (question_meta or {}).get("selected_slices") or None
        messages = [
            {
                "role": "system",
                "content": (
                    "You are simulating one internal collaborative interview panel. "
                    "Only the moderator speaks outwardly to the candidate. "
                    "Return strict JSON only and reply in Simplified Chinese. "
                    "Each panel role should assess the answer from its own focus, suggest follow-ups, and list evaluation points. "
                    'Return schema: {"panel":[{"role":"technical","role_key":"technical_deep_dive","focus":"",'
                    '"question_candidates":[""],"followup_candidates":[""],"evaluation_points":[""]}],'
                    '"moderator":{"score":7.8,"feedback":"","follow_up":false,"next_focus":"",'
                    '"selected_followups":[""],"reasoning_summary":"","feedback_style":"","difficulty_hint":""},'
                    '"metadata":{"mode":"panel","version":"panel_structured_v1",'
                    '"retrieved_slice_ids":[1,2],"fallback_allowed":true},'
                    '"strengths":[""],"gaps":[""]}. '
                    "The outward feedback must remain one moderator voice and be concise."
                    f"\n{AIService._build_panel_context(panel_snapshot)}\n"
                    f"{AIService._build_knowledge_base_context(knowledge_base, selected_slices=selected_slices)}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Resume JSON: {AIService._resume_snapshot(resume_context)}\n"
                    f"Chat history:\n{AIService._history_text(chat_history)}\n"
                    f"Current question: {question}\n"
                    f"Candidate answer: {answer}\n"
                    f"Lead role: {(question_meta or {}).get('lead_role') or '-'}\n"
                    f"Support roles: {', '.join((question_meta or {}).get('support_roles') or []) or '-'}\n"
                    f"Intent: {(question_meta or {}).get('intent') or '-'}\n"
                    f"Evaluation focus: {', '.join((question_meta or {}).get('evaluation_focus') or []) or '-'}\n"
                    f"Suggested followups: {', '.join((question_meta or {}).get('selected_followups') or []) or '-'}"
                ),
            },
        ]
        result = await AIService._chat(messages, temperature=0.3, ai_config=ai_config)
        payload = AIService._extract_json(result)
        normalized = AIService._normalize_panel_evaluation_payload(
            payload=payload,
            question_meta=question_meta,
            knowledge_base=knowledge_base,
            panel_snapshot=panel_snapshot,
        )
        logger.info(
            "Panel structured evaluation succeeded: lead_role=%s",
            (question_meta or {}).get("lead_role") or "-",
        )
        return normalized

    @staticmethod
    async def evaluate_answer_stream(
        question: str,
        answer: str,
        resume_context: dict,
        chat_history: list,
        knowledge_base: Optional[dict] = None,
        question_meta: Optional[Dict] = None,
        ai_config: Optional[Dict] = None,
    ):
        result = await AIService.evaluate_answer(
            question=question,
            answer=answer,
            resume_context=resume_context,
            chat_history=chat_history,
            knowledge_base=knowledge_base,
            question_meta=question_meta,
            ai_config=ai_config,
        )
        feedback = result.get("feedback", "")
        if feedback:
            yield feedback
        yield f'\n```json\n{{"score": {result.get("score", 5.0)}}}\n```'

    @staticmethod
    def _qa_text(questions_and_scores: Sequence[Dict]) -> str:
        lines = []
        for item in questions_and_scores:
            lines.append(f"Question: {item.get('question')}")
            lines.append(f"Answer: {item.get('answer') or '未回答'}")
            lines.append(f"Score: {item.get('score')}")
            if item.get("category"):
                lines.append(f"Category: {item.get('category')}")
            if item.get("lead_role"):
                lines.append(f"Lead role: {item.get('lead_role')}")
            if item.get("evaluation_focus"):
                lines.append(f"Evaluation focus: {', '.join(item.get('evaluation_focus') or [])}")
            if item.get("selected_followups"):
                lines.append(f"Selected followups: {', '.join(item.get('selected_followups') or [])}")
            if item.get("used_slice_ids"):
                lines.append(
                    f"Retrieved slice ids: {', '.join(str(v) for v in item.get('used_slice_ids') or [])}"
                )
            evaluation = item.get("evaluation") or {}
            if evaluation.get("strengths"):
                lines.append(f"Strengths: {', '.join(evaluation.get('strengths') or [])}")
            if evaluation.get("gaps"):
                lines.append(f"Gaps: {', '.join(evaluation.get('gaps') or [])}")
            if evaluation.get("next_focus"):
                lines.append(f"Next focus: {evaluation.get('next_focus')}")
            for panel_view in evaluation.get("panel_views") or []:
                if isinstance(panel_view, dict):
                    lines.append(
                        f"Panel view [{panel_view.get('role') or '-'}]: {panel_view.get('summary') or ''}"
                    )
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    async def generate_report(
        parsed_resume: dict,
        target_position: str,
        questions_and_scores: list,
        knowledge_base: Optional[dict] = None,
        panel_snapshot: Optional[Dict] = None,
        report_signals: Optional[Dict] = None,
        ai_config: Optional[Dict] = None,
    ) -> dict:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior interviewer writing a final mock-interview report. "
                    "Reply in Simplified Chinese and return pure JSON only. "
                    'Schema: {"summary":"","strengths":[""],"weaknesses":[""],'
                    '"suggestions":[""],"hire_recommendation":"","training_priorities":[""],"common_gaps":[""]}. '
                    f"\n{AIService._build_knowledge_base_context(knowledge_base)}\n"
                    f"{AIService._build_report_signal_context(report_signals)}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Target position: {target_position}\n"
                    f"Resume JSON: {AIService._resume_snapshot(parsed_resume)}\n"
                    f"Interview records:\n{AIService._qa_text(questions_and_scores)}"
                ),
            },
        ]
        result = await AIService._chat(messages, temperature=0.35, ai_config=ai_config)
        return AIService._extract_json(result)

    @staticmethod
    async def generate_panel_report(
        parsed_resume: dict,
        target_position: str,
        questions_and_scores: list,
        knowledge_base: Optional[dict] = None,
        panel_snapshot: Optional[Dict] = None,
        report_signals: Optional[Dict] = None,
        ai_config: Optional[Dict] = None,
    ) -> dict:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are summarizing a collaborative internal interview panel while keeping one unified outward report. "
                    "Reply in Simplified Chinese and return pure JSON only. "
                    'Schema: {"summary":"","strengths":[""],"weaknesses":[""],"suggestions":[""],'
                    '"hire_recommendation":"","training_priorities":[""],'
                    '"common_gaps":[""],'
                    '"panel_summary":[{"role":"technical_deep_dive","title":"技术深挖","summary":""}]}. '
                    f"\n{AIService._build_panel_context(panel_snapshot)}\n"
                    f"{AIService._build_knowledge_base_context(knowledge_base)}\n"
                    f"{AIService._build_report_signal_context(report_signals)}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Target position: {target_position}\n"
                    f"Resume JSON: {AIService._resume_snapshot(parsed_resume)}\n"
                    f"Interview records:\n{AIService._qa_text(questions_and_scores)}"
                ),
            },
        ]
        result = await AIService._chat(messages, temperature=0.3, ai_config=ai_config)
        return AIService._extract_json(result)
