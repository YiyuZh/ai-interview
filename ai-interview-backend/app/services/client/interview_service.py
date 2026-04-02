from collections import Counter
import json
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import delete as sql_delete
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.http_exceptions import NotFoundError, ValidationError
from app.models.interview import Interview
from app.models.interview_message import InterviewMessage
from app.models.position_knowledge_base import PositionKnowledgeBase
from app.models.resume import Resume
from app.services.client.ai_service import AIService
from app.services.client.position_knowledge_base_slice_service import (
    position_knowledge_base_slice_service,
)

logger = logging.getLogger(__name__)


PANEL_ROLE_SPECS = [
    {
        "key": "technical_deep_dive",
        "name": "Technical Deep Dive",
        "focus": "Probe core principles, technical trade-offs, and hard engineering details.",
    },
    {
        "key": "project_follow_up",
        "name": "Project Follow-up",
        "focus": "Verify ownership, real contribution, trade-offs, and project retrospection.",
    },
    {
        "key": "business_scenario",
        "name": "Business Scenario",
        "focus": "Test whether technical thinking can be grounded in realistic business context.",
    },
    {
        "key": "behavior_expression",
        "name": "Behavior & Communication",
        "focus": "Observe structure, collaboration, growth mindset, and communication quality.",
    },
    {
        "key": "pressure_challenge",
        "name": "Pressure Challenge",
        "focus": "Test boundary handling, risk awareness, pressure response, and decision trade-offs.",
    },
]

QUESTION_TEMPLATES = {
    "opening_intro": {
        "stage": "opening",
        "category": "self-intro",
        "lead_role": "behavior_expression",
        "support_roles": ["project_follow_up"],
        "intent": "Use the self-introduction to quickly assess background fit, clarity, and motivation.",
        "evaluation_focus": ["structured expression", "role motivation", "background highlights"],
    },
    "project_core": {
        "stage": "project",
        "category": "project",
        "lead_role": "project_follow_up",
        "support_roles": ["technical_deep_dive"],
        "intent": "Deep-dive the most important project to verify ownership, trade-offs, and retrospection quality.",
        "evaluation_focus": ["ownership", "solution trade-offs", "project retrospection"],
    },
    "technical_core": {
        "stage": "technical",
        "category": "technical",
        "lead_role": "technical_deep_dive",
        "support_roles": ["project_follow_up"],
        "intent": "Validate mastery of core knowledge and depth of understanding.",
        "evaluation_focus": ["core principles", "accuracy", "technical depth"],
    },
    "business_scenario": {
        "stage": "scenario",
        "category": "system-design",
        "lead_role": "business_scenario",
        "support_roles": ["technical_deep_dive"],
        "intent": "Place the candidate in a realistic business scenario to test execution quality.",
        "evaluation_focus": ["business understanding", "solution landing", "stability awareness"],
    },
    "behavior_growth": {
        "stage": "behavior",
        "category": "behavior",
        "lead_role": "behavior_expression",
        "support_roles": ["project_follow_up"],
        "intent": "Evaluate collaboration, communication, reflection, and growth potential.",
        "evaluation_focus": ["communication", "collaboration reflection", "growth potential"],
    },
    "pressure_tradeoff": {
        "stage": "scenario",
        "category": "system-design",
        "lead_role": "pressure_challenge",
        "support_roles": ["technical_deep_dive", "business_scenario"],
        "intent": "Assess boundary awareness and trade-offs under pressure.",
        "evaluation_focus": ["risk trade-offs", "stability", "pressure response"],
    },
    "technical_debug": {
        "stage": "technical",
        "category": "technical",
        "lead_role": "technical_deep_dive",
        "support_roles": ["pressure_challenge"],
        "intent": "Use debugging or optimization questions to verify diagnosis and engineering experience.",
        "evaluation_focus": ["debugging approach", "engineering experience", "optimization ability"],
    },
    "project_ownership": {
        "stage": "project",
        "category": "project",
        "lead_role": "project_follow_up",
        "support_roles": ["behavior_expression"],
        "intent": "Further verify role boundaries, leadership level, and delivery outcomes in projects.",
        "evaluation_focus": ["role boundary", "result orientation", "retrospective quality"],
    },
    "scenario_tradeoff": {
        "stage": "scenario",
        "category": "system-design",
        "lead_role": "business_scenario",
        "support_roles": ["pressure_challenge"],
        "intent": "Use business changes and resource limits to validate solution trade-offs.",
        "evaluation_focus": ["scenario fit", "priority judgment", "resource trade-offs"],
    },
    "closing_reflection": {
        "stage": "closing",
        "category": "behavior",
        "lead_role": "behavior_expression",
        "support_roles": ["pressure_challenge"],
        "intent": "Close the interview by checking self-awareness and most urgent training priorities.",
        "evaluation_focus": ["self-awareness", "summary ability", "training direction"],
    },
}

QUESTION_ORDERS = {
    "easy": [
        "opening_intro",
        "project_core",
        "technical_core",
        "behavior_growth",
        "project_ownership",
        "technical_debug",
        "business_scenario",
        "scenario_tradeoff",
        "closing_reflection",
        "closing_reflection",
    ],
    "medium": [
        "opening_intro",
        "project_core",
        "technical_core",
        "business_scenario",
        "behavior_growth",
        "pressure_tradeoff",
        "technical_debug",
        "project_ownership",
        "scenario_tradeoff",
        "closing_reflection",
    ],
    "hard": [
        "opening_intro",
        "project_core",
        "technical_core",
        "pressure_tradeoff",
        "business_scenario",
        "technical_debug",
        "project_ownership",
        "scenario_tradeoff",
        "technical_core",
        "closing_reflection",
    ],
}

PANEL_ROLE_TITLES = {
    "technical_deep_dive": "Technical Deep Dive",
    "project_follow_up": "Project Follow-up",
    "business_scenario": "Business Scenario",
    "behavior_expression": "Behavior & Communication",
    "pressure_challenge": "Pressure Challenge",
}


class InterviewService:
    @staticmethod
    def _load_resume_payload(resume: Resume) -> Dict[str, Any]:
        payload = (resume.parsed_content or "").strip()
        if not payload:
            raise ValidationError(message="开始面试失败：简历解析结果为空，请重新解析后再试")
        try:
            parsed_resume = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                message="开始面试失败：简历解析结果异常，请重新上传简历或重新解析"
            ) from exc
        if not isinstance(parsed_resume, dict):
            raise ValidationError(
                message="开始面试失败：简历解析结果异常，请重新上传简历或重新解析"
            )
        return parsed_resume

    @staticmethod
    def _format_start_interview_error(detail: Optional[str]) -> str:
        message = (detail or "").strip()
        if not message:
            return "开始面试失败：题目生成服务异常，请稍后重试"
        if message.startswith("开始面试失败："):
            return message
        if "题目生成数量不足" in message:
            return "开始面试失败：当前模型返回的题目数量不足，请切换模型或稍后重试"
        if "题目生成失败" in message:
            return "开始面试失败：AI 题目生成失败，请更换模型或稍后重试"
        if (
            "API Key" in message
            or "API Token" in message
            or "Base URL" in message
            or "模型名" in message
            or "连接 " in message
            or "请求参数错误" in message
        ):
            return f"开始面试失败：{message}"
        if "岗位知识库" in message or "简历" in message:
            return message if message.startswith("开始面试失败：") else f"开始面试失败：{message}"
        return f"开始面试失败：{message}"

    @staticmethod
    def _serialize_knowledge_base(knowledge_base: Optional[PositionKnowledgeBase]) -> Optional[Dict]:
        if not knowledge_base:
            return None
        scope = knowledge_base.scope or "private"
        return {
            "id": knowledge_base.id,
            "title": knowledge_base.title,
            "target_position": knowledge_base.target_position,
            "knowledge_content": knowledge_base.knowledge_content,
            "focus_points": knowledge_base.focus_points,
            "interviewer_prompt": knowledge_base.interviewer_prompt,
            "is_active": knowledge_base.is_active,
            "scope": scope,
            "source_label": "后台公共知识库" if scope == "public" else "我的知识库",
        }

    @staticmethod
    def _build_panel_snapshot(
        mode: str,
        requested_panel: bool = False,
        fallback_reason: Optional[str] = None,
    ) -> Dict:
        snapshot = {
            "mode": mode,
            "requested_panel": requested_panel or mode == "panel",
            "display_name": "内部多面试官协同" if mode == "panel" else "单面试官模式",
            "moderator_name": "主持人面试官",
        }
        if mode == "panel":
            snapshot["roles"] = PANEL_ROLE_SPECS
        if fallback_reason:
            snapshot["fallback_reason"] = fallback_reason
        return snapshot

    @staticmethod
    def _compact_slice(item: Dict) -> Dict:
        return {
            "slice_id": item.get("slice_id"),
            "title": item.get("title"),
            "content": item.get("content"),
            "slice_type": item.get("slice_type"),
            "source_section": item.get("source_section"),
            "source_scope": item.get("source_scope"),
            "difficulty": item.get("difficulty"),
            "priority": item.get("priority"),
            "stage_tags": item.get("stage_tags") or [],
            "role_tags": item.get("role_tags") or [],
            "topic_tags": item.get("topic_tags") or [],
            "skill_tags": item.get("skill_tags") or [],
            "scene_tags": item.get("scene_tags") or [],
            "keywords": item.get("keywords") or [],
            "routing_score": item.get("routing_score"),
            "routing_reasons": item.get("routing_reasons") or [],
        }

    @staticmethod
    def _slice_label(item: Dict) -> str:
        title = str(item.get("title") or "").strip()
        if title:
            return title
        slice_id = item.get("slice_id")
        if slice_id:
            return f"切片 #{slice_id}"
        return "知识切片"

    @staticmethod
    def _build_evidence_trace(selected_slices: Sequence[Dict], used_slice_ids: Optional[Sequence[int]] = None) -> List[Dict]:
        selected_ids = set()
        for value in used_slice_ids or []:
            try:
                selected_ids.add(int(value))
            except (TypeError, ValueError):
                continue

        trace = []
        for item in selected_slices or []:
            try:
                slice_id = int(item.get("slice_id"))
            except (TypeError, ValueError):
                slice_id = None
            reasons = [str(reason).strip() for reason in (item.get("routing_reasons") or []) if str(reason).strip()]
            trace.append(
                {
                    "slice_id": slice_id,
                    "title": InterviewService._slice_label(item),
                    "source_section": item.get("source_section") or item.get("slice_type"),
                    "reason_summary": "；".join(reasons[:3]),
                    "reasons": reasons[:4],
                    "quote": str(item.get("content") or "").strip()[:120],
                    "is_selected": bool(slice_id and slice_id in selected_ids) if selected_ids else True,
                }
            )
        return trace

    @staticmethod
    def _build_evidence_summary(selected_slices: Sequence[Dict], used_slice_ids: Optional[Sequence[int]] = None) -> List[str]:
        trace = InterviewService._build_evidence_trace(selected_slices, used_slice_ids=used_slice_ids)
        summary = []
        for item in trace[:3]:
            label = item.get("title") or "知识切片"
            reason = item.get("reason_summary") or "已命中相关岗位证据"
            summary.append(f"{label}：{reason}")
        return summary

    @staticmethod
    def _resume_route_text(parsed_resume: Dict) -> str:
        parts = []
        if parsed_resume.get("summary"):
            parts.append(parsed_resume["summary"])
        if parsed_resume.get("education"):
            parts.append(parsed_resume["education"])
        if parsed_resume.get("skills"):
            parts.append(" ".join(parsed_resume.get("skills")[:12]))
        if parsed_resume.get("projects"):
            parts.append(" ".join(parsed_resume.get("projects")[:4]))
        if parsed_resume.get("experience"):
            parts.append(" ".join(parsed_resume.get("experience")[:4]))
        return "\n".join(parts)

    @staticmethod
    def _build_question_plan(total_questions: int, difficulty: str) -> List[Dict]:
        order = QUESTION_ORDERS.get(difficulty, QUESTION_ORDERS["medium"])
        plan = []
        for index, key in enumerate(order[:total_questions]):
            item = QUESTION_TEMPLATES[key].copy()
            item["index"] = index
            plan.append(item)
        return plan

    @staticmethod
    def _route_question_plan(
        question_plan: List[Dict],
        knowledge_base: Optional[Dict],
        parsed_resume: Dict,
        target_position: str,
        difficulty: str,
    ) -> List[Dict]:
        if not knowledge_base:
            return [{**item, "selected_slices": []} for item in question_plan]

        slices = knowledge_base.get("slices") or []
        if not slices:
            return [{**item, "selected_slices": []} for item in question_plan]

        routed = []
        top_k = 2 if len(question_plan) >= 7 else 3
        resume_text = InterviewService._resume_route_text(parsed_resume)
        resume_skills = parsed_resume.get("skills") or []
        resume_projects = parsed_resume.get("projects") or []
        for item in question_plan:
            query_text = "\n".join(
                [
                    target_position,
                    resume_text,
                    item.get("intent") or "",
                    " ".join(item.get("evaluation_focus") or []),
                ]
            )
            try:
                selected = position_knowledge_base_slice_service.rank_slices(
                    slices=slices,
                    query_text=query_text,
                    stage=item.get("stage"),
                    role=item.get("lead_role"),
                    scene=item.get("category") or item.get("stage"),
                    difficulty=difficulty,
                    skills=resume_skills[:8],
                    topics=[target_position, *(resume_projects[:2])],
                    top_k=top_k,
                )
                if not selected:
                    selected = position_knowledge_base_slice_service.rank_slices(
                        slices=slices,
                        query_text=query_text,
                        difficulty=difficulty,
                        skills=resume_skills[:6],
                        topics=[target_position],
                        top_k=2,
                    )
            except Exception as exc:
                logger.warning("Knowledge slice routing failed for stage=%s: %s", item.get("stage"), exc)
                knowledge_base["slices"] = []
                knowledge_base["slice_count"] = 0
                knowledge_base["routing_strategy"] = "full_text_fallback"
                selected = []
            routed.append(
                {
                    **item,
                    "selected_slices": [InterviewService._compact_slice(slice_item) for slice_item in selected],
                }
            )
        return routed

    @staticmethod
    def _normalize_questions(
        raw_questions: List[Dict],
        question_plan: List[Dict],
        interview_mode: str,
    ) -> List[Dict]:
        if len(raw_questions) < len(question_plan):
            raise ValidationError(message="AI 题目生成数量不足，请稍后重试")

        normalized = []
        for index, plan in enumerate(question_plan):
            raw = raw_questions[index] or {}
            if isinstance(raw, str):
                raw = {"question": raw}
            question_text = (raw.get("question") or "").strip()
            if not question_text:
                raise ValidationError(message="AI 题目生成失败，请稍后重试")

            support_roles = raw.get("support_roles") or plan.get("support_roles") or []
            if isinstance(support_roles, str):
                support_roles = [support_roles]

            evaluation_focus = raw.get("evaluation_focus") or plan.get("evaluation_focus") or []
            if isinstance(evaluation_focus, str):
                evaluation_focus = [evaluation_focus]

            selected_slices = plan.get("selected_slices") or []
            requested_ids = raw.get("used_slice_ids") or raw.get("selected_slice_ids") or []
            if requested_ids:
                matched = [
                    item for item in selected_slices if item.get("slice_id") in set(requested_ids)
                ]
                if matched:
                    selected_slices = matched

            normalized.append(
                {
                    "index": index,
                    "question": question_text,
                    "category": raw.get("category") or plan.get("category"),
                    "stage": raw.get("stage") or plan.get("stage"),
                    "lead_role": raw.get("lead_role") or plan.get("lead_role"),
                    "support_roles": support_roles,
                    "intent": raw.get("intent") or plan.get("intent"),
                    "evaluation_focus": evaluation_focus,
                    "selected_slices": selected_slices,
                    "used_slice_ids": requested_ids or [],
                    "evidence_trace": InterviewService._build_evidence_trace(
                        selected_slices,
                        used_slice_ids=requested_ids or [],
                    ),
                    "evidence_summary": InterviewService._build_evidence_summary(
                        selected_slices,
                        used_slice_ids=requested_ids or [],
                    ),
                    "selected_followups": raw.get("selected_followups") or [],
                    "difficulty_hint": raw.get("difficulty_hint"),
                    "panel_context": raw.get("panel_context") or {},
                    "panel_reasoning_summary": raw.get("panel_reasoning_summary"),
                    "interview_mode": interview_mode,
                    "answer": None,
                    "score": None,
                    "feedback": None,
                    "evaluation": None,
                }
            )
        return normalized

    @staticmethod
    def _serialize_questions(questions: List[Dict]) -> List[Dict]:
        return json.loads(json.dumps(questions, ensure_ascii=False))

    @staticmethod
    def _build_question_scores(questions: List[Dict]) -> List[Dict]:
        items = []
        for question in questions:
            items.append(
                {
                    "question": question.get("question"),
                    "score": float(question.get("score") or 0),
                    "feedback": question.get("feedback") or "",
                    "category": question.get("category"),
                    "lead_role": question.get("lead_role"),
                }
            )
        return items

    @staticmethod
    def _build_qa_data(questions: List[Dict]) -> List[Dict]:
        qa_data = []
        for question in questions:
            qa_data.append(
                {
                    "question": question.get("question"),
                    "answer": question.get("answer") or "未回答",
                    "score": float(question.get("score") or 0),
                    "feedback": question.get("feedback") or "",
                    "category": question.get("category"),
                    "stage": question.get("stage"),
                    "lead_role": question.get("lead_role"),
                    "support_roles": question.get("support_roles") or [],
                    "intent": question.get("intent"),
                    "evaluation_focus": question.get("evaluation_focus") or [],
                    "selected_slices": question.get("selected_slices") or [],
                    "used_slice_ids": question.get("used_slice_ids") or [],
                    "evidence_trace": question.get("evidence_trace") or [],
                    "evidence_summary": question.get("evidence_summary") or [],
                    "selected_followups": question.get("selected_followups") or [],
                    "panel_context": question.get("panel_context") or {},
                    "evaluation": question.get("evaluation") or {},
                }
            )
        return qa_data

    @staticmethod
    def _unique_strings(values: Sequence[Any], limit: int = 8) -> List[str]:
        ordered: List[str] = []
        for value in values or []:
            if value is None:
                continue
            text = str(value).strip()
            if text and text not in ordered:
                ordered.append(text)
            if len(ordered) >= limit:
                break
        return ordered

    @staticmethod
    def _question_slice_ids(question_meta: Optional[Dict]) -> List[int]:
        ordered: List[int] = []
        for item in (question_meta or {}).get("selected_slices") or []:
            try:
                slice_id = int(item.get("slice_id"))
            except (TypeError, ValueError):
                continue
            if slice_id not in ordered:
                ordered.append(slice_id)
        for value in (question_meta or {}).get("used_slice_ids") or []:
            try:
                slice_id = int(value)
            except (TypeError, ValueError):
                continue
            if slice_id not in ordered:
                ordered.append(slice_id)
        return ordered

    @staticmethod
    def _extract_weakness_terms(
        current_question_meta: Dict,
        evaluation: Optional[Dict],
    ) -> List[str]:
        terms: List[str] = []
        if current_question_meta.get("evaluation_focus"):
            terms.extend(current_question_meta.get("evaluation_focus") or [])
        if current_question_meta.get("selected_followups"):
            terms.extend(current_question_meta.get("selected_followups") or [])
        if evaluation:
            terms.extend(evaluation.get("gaps") or [])
            if evaluation.get("next_focus"):
                terms.append(evaluation.get("next_focus"))
            for item in evaluation.get("panel_views") or []:
                if isinstance(item, dict) and item.get("summary"):
                    terms.append(item.get("summary"))
        return InterviewService._unique_strings(terms, limit=10)

    @staticmethod
    def _extract_followup_candidates(
        current_question_meta: Dict,
        evaluation: Optional[Dict],
    ) -> List[str]:
        ordered: List[str] = []

        def add_many(values):
            for value in values or []:
                text = str(value).strip()
                if text and text not in ordered:
                    ordered.append(text)

        add_many((evaluation or {}).get("moderator", {}).get("selected_followups") or [])
        add_many((evaluation or {}).get("selected_followups") or [])
        for item in (evaluation or {}).get("panel") or []:
            if isinstance(item, dict):
                add_many(item.get("followup_candidates") or [])
        add_many(current_question_meta.get("selected_followups") or [])
        return ordered[:5]

    @staticmethod
    def _apply_followup_to_next_question(
        current_question_meta: Dict,
        next_question_meta: Dict,
        evaluation: Optional[Dict],
    ) -> Dict:
        followups = InterviewService._extract_followup_candidates(current_question_meta, evaluation)
        if not followups:
            return next_question_meta

        next_meta = dict(next_question_meta)
        next_meta["question"] = followups[0]
        next_meta["stage"] = current_question_meta.get("stage") or next_meta.get("stage")
        next_meta["category"] = current_question_meta.get("category") or next_meta.get("category")
        next_meta["lead_role"] = current_question_meta.get("lead_role") or next_meta.get("lead_role")
        next_meta["support_roles"] = (
            current_question_meta.get("support_roles") or next_meta.get("support_roles") or []
        )
        next_meta["intent"] = (
            (evaluation or {}).get("next_focus")
            or current_question_meta.get("intent")
            or next_meta.get("intent")
        )
        next_meta["evaluation_focus"] = (
            (evaluation or {}).get("gaps")
            or current_question_meta.get("evaluation_focus")
            or next_meta.get("evaluation_focus")
            or []
        )
        next_meta["selected_followups"] = followups[1:]
        next_meta["followup_source_question_index"] = current_question_meta.get("index")
        next_meta["is_dynamic_followup"] = True

        panel_context = dict(current_question_meta.get("panel_context") or {})
        moderator = dict(panel_context.get("moderator") or {})
        moderator["selected_question"] = followups[0]
        moderator["selected_followups"] = followups[1:]
        if (evaluation or {}).get("moderator", {}).get("reasoning_summary"):
            moderator["reasoning_summary"] = evaluation["moderator"]["reasoning_summary"]
        if (evaluation or {}).get("moderator", {}).get("difficulty_hint"):
            moderator["difficulty_hint"] = evaluation["moderator"]["difficulty_hint"]
        if moderator:
            panel_context["moderator"] = moderator
            next_meta["panel_context"] = panel_context

        return next_meta

    @staticmethod
    def _reroute_question_slices(
        question_meta: Dict,
        knowledge_base: Optional[Dict],
        parsed_resume: Dict,
        target_position: str,
        difficulty: str,
        context_terms: Optional[Sequence[str]] = None,
    ) -> Dict:
        if not knowledge_base or not (knowledge_base.get("slices") or []):
            return question_meta

        resume_text = InterviewService._resume_route_text(parsed_resume)
        resume_skills = parsed_resume.get("skills") or []
        resume_projects = parsed_resume.get("projects") or []
        query_parts = [
            target_position,
            resume_text,
            question_meta.get("question") or "",
            question_meta.get("intent") or "",
            " ".join(question_meta.get("evaluation_focus") or []),
            " ".join(context_terms or []),
        ]
        try:
            selected = position_knowledge_base_slice_service.rank_slices(
                slices=knowledge_base.get("slices") or [],
                query_text="\n".join(part for part in query_parts if part),
                stage=question_meta.get("stage"),
                role=question_meta.get("lead_role"),
                scene=question_meta.get("category") or question_meta.get("stage"),
                difficulty=difficulty,
                skills=resume_skills[:8],
                topics=[target_position, *(resume_projects[:2])],
                weakness_terms=context_terms or [],
                top_k=2,
            )
        except Exception as exc:
            logger.warning("Question slice reroute failed for question index=%s: %s", question_meta.get("index"), exc)
            return question_meta

        if not selected:
            return question_meta

        next_meta = dict(question_meta)
        next_meta["selected_slices"] = [
            InterviewService._compact_slice(slice_item) for slice_item in selected
        ]
        next_meta["used_slice_ids"] = [
            item.get("slice_id") for item in next_meta["selected_slices"] if item.get("slice_id")
        ]
        next_meta["evidence_trace"] = InterviewService._build_evidence_trace(
            next_meta["selected_slices"],
            used_slice_ids=next_meta["used_slice_ids"],
        )
        next_meta["evidence_summary"] = InterviewService._build_evidence_summary(
            next_meta["selected_slices"],
            used_slice_ids=next_meta["used_slice_ids"],
        )
        panel_context = dict(next_meta.get("panel_context") or {})
        metadata = dict(panel_context.get("metadata") or {})
        metadata["retrieved_slice_ids"] = next_meta["used_slice_ids"]
        if metadata:
            panel_context["metadata"] = metadata
            next_meta["panel_context"] = panel_context
        return next_meta

    @staticmethod
    def _build_report_signals(questions: List[Dict]) -> Dict:
        gap_counter: Counter = Counter()
        strength_counter: Counter = Counter()
        slice_ids: List[int] = []
        training_priorities: List[str] = []
        panel_notes: Dict[str, List[str]] = {}
        evidence_summary: List[str] = []
        evidence_question_count = 0

        for question in questions:
            evaluation = question.get("evaluation") or {}
            for item in evaluation.get("gaps") or []:
                text = str(item).strip()
                if text:
                    gap_counter[text] += 1
            for item in evaluation.get("strengths") or []:
                text = str(item).strip()
                if text:
                    strength_counter[text] += 1
            next_focus = str(evaluation.get("next_focus") or "").strip()
            if next_focus:
                training_priorities.append(next_focus)

            for value in question.get("used_slice_ids") or []:
                try:
                    slice_id = int(value)
                except (TypeError, ValueError):
                    continue
                if slice_id not in slice_ids:
                    slice_ids.append(slice_id)

            question_evidence_summary = InterviewService._unique_strings(
                question.get("evidence_summary") or [],
                limit=3,
            )
            if question_evidence_summary:
                evidence_question_count += 1
                for item in question_evidence_summary:
                    if item not in evidence_summary:
                        evidence_summary.append(item)

            for item in evaluation.get("panel_views") or []:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "").strip()
                summary = str(item.get("summary") or "").strip()
                if role and summary:
                    panel_notes.setdefault(role, []).append(summary)

        panel_summary = []
        for role, summaries in panel_notes.items():
            panel_summary.append(
                {
                    "role": role,
                    "title": PANEL_ROLE_TITLES.get(role, role),
                    "summary": " ".join(InterviewService._unique_strings(summaries, limit=3)),
                }
            )

        return {
            "common_gaps": [item for item, _ in gap_counter.most_common(5)],
            "common_strengths": [item for item, _ in strength_counter.most_common(5)],
            "training_priorities": InterviewService._unique_strings(
                [*training_priorities, *[item for item, _ in gap_counter.most_common(3)]],
                limit=5,
            ),
            "panel_summary": panel_summary,
            "retrieved_slice_ids": slice_ids,
            "evidence_summary": evidence_summary[:6],
            "evidence_stats": {
                "questions_with_evidence": evidence_question_count,
                "total_questions": len(questions),
                "retrieved_slice_count": len(slice_ids),
            },
        }

    @staticmethod
    def _merge_report_defaults(
        report: Dict,
        report_signals: Dict,
        interview_mode: str,
    ) -> Dict:
        merged = dict(report or {})
        if not merged.get("weaknesses") and report_signals.get("common_gaps"):
            merged["weaknesses"] = report_signals["common_gaps"]
        if not merged.get("strengths") and report_signals.get("common_strengths"):
            merged["strengths"] = report_signals["common_strengths"]
        if not merged.get("training_priorities") and report_signals.get("training_priorities"):
            merged["training_priorities"] = report_signals["training_priorities"]
        if not merged.get("common_gaps") and report_signals.get("common_gaps"):
            merged["common_gaps"] = report_signals["common_gaps"]
        if interview_mode == "panel" and not merged.get("panel_summary") and report_signals.get("panel_summary"):
            merged["panel_summary"] = report_signals["panel_summary"]
        if not merged.get("evidence_summary") and report_signals.get("evidence_summary"):
            merged["evidence_summary"] = report_signals["evidence_summary"]
        if not merged.get("evidence_stats") and report_signals.get("evidence_stats"):
            merged["evidence_stats"] = report_signals["evidence_stats"]
        return merged

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 28) -> List[str]:
        content = text or ""
        if not content:
            return [""]
        return [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)]

    @staticmethod
    async def _resolve_knowledge_base(
        db: AsyncSession,
        user_id: int,
        target_position: str,
        knowledge_base_id: Optional[int] = None,
    ) -> Optional[Dict]:
        if knowledge_base_id:
            result = await db.execute(
                select(PositionKnowledgeBase).where(
                    PositionKnowledgeBase.id == knowledge_base_id,
                    or_(
                        PositionKnowledgeBase.user_id == user_id,
                        PositionKnowledgeBase.scope == "public",
                    ),
                )
            )
            knowledge_base = result.scalar_one_or_none()
            if not knowledge_base:
                raise NotFoundError(message="岗位知识库不存在")
            if not knowledge_base.is_active:
                raise ValidationError(message="所选岗位知识库已停用，请重新选择")
        else:
            normalized_target = (target_position or "").strip()
            if not normalized_target:
                return None
            result = await db.execute(
                select(PositionKnowledgeBase)
                .where(
                    PositionKnowledgeBase.user_id == user_id,
                    PositionKnowledgeBase.scope == "private",
                    PositionKnowledgeBase.is_active.is_(True),
                    PositionKnowledgeBase.target_position.ilike(f"%{normalized_target}%"),
                )
                .order_by(PositionKnowledgeBase.updated_at.desc())
            )
            knowledge_base = result.scalars().first()
            if not knowledge_base:
                result = await db.execute(
                    select(PositionKnowledgeBase)
                    .where(
                        PositionKnowledgeBase.scope == "public",
                        PositionKnowledgeBase.is_active.is_(True),
                        PositionKnowledgeBase.target_position.ilike(f"%{normalized_target}%"),
                    )
                    .order_by(PositionKnowledgeBase.updated_at.desc())
                )
                knowledge_base = result.scalars().first()

        payload = InterviewService._serialize_knowledge_base(knowledge_base)
        if not payload:
            return None
        try:
            slices = await position_knowledge_base_slice_service.list_for_knowledge_base(db, knowledge_base.id)
            payload["slices"] = [InterviewService._compact_slice(item) for item in slices]
            payload["slice_count"] = len(payload["slices"])
            payload["routing_strategy"] = (
                "structured_slice_routing_v1" if payload["slices"] else "full_text_fallback"
            )
        except Exception as exc:
            logger.warning("Knowledge slice loading failed for knowledge_base=%s: %s", knowledge_base.id, exc)
            payload["slices"] = []
            payload["slice_count"] = 0
            payload["routing_strategy"] = "full_text_fallback"
        return payload

    @staticmethod
    async def start_interview(
        db: AsyncSession,
        user_id: int,
        resume_id: int,
        target_position: str,
        knowledge_base_id: Optional[int],
        difficulty: str,
        total_questions: int,
        multi_interviewer_enabled: bool = False,
        ai_config: Optional[Dict] = None,
    ) -> Dict:
        result = await db.execute(
            select(Resume).where(
                Resume.id == resume_id,
                Resume.user_id == user_id,
            )
        )
        resume = result.scalar_one_or_none()
        if not resume:
            raise NotFoundError(message="简历不存在")
        if resume.status != "completed":
            raise ValidationError(message="简历尚未解析完成")

        parsed_resume = InterviewService._load_resume_payload(resume)
        knowledge_base_context = await InterviewService._resolve_knowledge_base(
            db=db,
            user_id=user_id,
            target_position=target_position,
            knowledge_base_id=knowledge_base_id,
        )
        question_plan = InterviewService._route_question_plan(
            question_plan=InterviewService._build_question_plan(total_questions, difficulty),
            knowledge_base=knowledge_base_context,
            parsed_resume=parsed_resume,
            target_position=target_position,
            difficulty=difficulty,
        )

        interview_mode = "panel" if multi_interviewer_enabled else "single"
        panel_snapshot = InterviewService._build_panel_snapshot(interview_mode)

        try:
            if interview_mode == "panel":
                panel_payload = await AIService.generate_panel_questions(
                    parsed_resume=parsed_resume,
                    target_position=target_position,
                    difficulty=difficulty,
                    count=total_questions,
                    question_plan=question_plan,
                    knowledge_base=knowledge_base_context,
                    panel_snapshot=panel_snapshot,
                    ai_config=ai_config,
                )
                if panel_payload.get("moderator_style"):
                    panel_snapshot["moderator_style"] = panel_payload["moderator_style"]
                if panel_payload.get("metadata"):
                    panel_snapshot["structured_output"] = {
                        "version": panel_payload["metadata"].get("version"),
                        "retrieved_slice_ids": panel_payload["metadata"].get("retrieved_slice_ids") or [],
                    }
                if panel_payload.get("moderator", {}).get("reasoning_summary"):
                    panel_snapshot["moderator_reasoning_summary"] = panel_payload["moderator"]["reasoning_summary"]
                questions = InterviewService._normalize_questions(
                    raw_questions=panel_payload.get("questions") or [],
                    question_plan=question_plan,
                    interview_mode="panel",
                )
            else:
                raw_questions = await AIService.generate_questions(
                    parsed_resume=parsed_resume,
                    target_position=target_position,
                    difficulty=difficulty,
                    count=total_questions,
                    knowledge_base=knowledge_base_context,
                    question_plan=question_plan,
                    ai_config=ai_config,
                )
                questions = InterviewService._normalize_questions(
                    raw_questions=raw_questions,
                    question_plan=question_plan,
                    interview_mode="single",
                )
        except ValidationError as exc:
            raise ValidationError(
                message=InterviewService._format_start_interview_error(exc.detail)
            ) from exc
        except Exception as exc:
            if interview_mode == "panel":
                logger.warning("Panel question generation failed, fallback to single mode: %s", exc)
                try:
                    raw_questions = await AIService.generate_questions(
                        parsed_resume=parsed_resume,
                        target_position=target_position,
                        difficulty=difficulty,
                        count=total_questions,
                        knowledge_base=knowledge_base_context,
                        question_plan=question_plan,
                        ai_config=ai_config,
                    )
                    questions = InterviewService._normalize_questions(
                        raw_questions=raw_questions,
                        question_plan=question_plan,
                        interview_mode="single",
                    )
                    interview_mode = "single"
                    panel_snapshot = InterviewService._build_panel_snapshot(
                        mode="single",
                        requested_panel=True,
                        fallback_reason="panel_generation_failed",
                    )
                except ValidationError as inner_exc:
                    raise ValidationError(
                        message=InterviewService._format_start_interview_error(inner_exc.detail)
                    ) from inner_exc
                except Exception as inner_exc:
                    logger.exception("Single question fallback failed: %s", inner_exc)
                    raise ValidationError(
                        message="开始面试失败：题目生成服务异常，请稍后重试"
                    ) from inner_exc
            else:
                logger.exception("Question generation failed: %s", exc)
                raise ValidationError(message="开始面试失败：题目生成服务异常，请稍后重试") from exc

        questions = InterviewService._serialize_questions(questions)
        interview = Interview(
            user_id=user_id,
            resume_id=resume_id,
            knowledge_base_id=knowledge_base_context["id"] if knowledge_base_context else None,
            target_position=target_position,
            difficulty=difficulty,
            total_questions=total_questions,
            current_question_index=0,
            interview_mode=interview_mode,
            questions_data=questions,
            knowledge_base_snapshot=knowledge_base_context,
            panel_snapshot=panel_snapshot,
            status="in_progress",
        )
        db.add(interview)
        await db.commit()
        await db.refresh(interview)

        first_question = questions[0]["question"]
        db.add(
            InterviewMessage(
                interview_id=interview.id,
                role="interviewer",
                content=first_question,
                question_index=0,
            )
        )
        await db.commit()

        return {
            "interview_id": interview.id,
            "first_question": first_question,
            "question_index": 0,
            "total_questions": total_questions,
            "knowledge_base_title": knowledge_base_context["title"] if knowledge_base_context else None,
            "interview_mode": interview_mode,
        }

    @staticmethod
    async def submit_answer(
        db: AsyncSession,
        user_id: int,
        interview_id: int,
        answer: str,
        ai_config: Optional[Dict] = None,
    ) -> Dict:
        result = await db.execute(
            select(Interview).where(
                Interview.id == interview_id,
                Interview.user_id == user_id,
            )
        )
        interview = result.scalar_one_or_none()
        if not interview:
            raise NotFoundError(message="面试记录不存在")
        if interview.status == "completed":
            raise ValidationError(message="面试已结束")

        resume_result = await db.execute(select(Resume).where(Resume.id == interview.resume_id))
        resume = resume_result.scalar_one_or_none()
        parsed_resume = json.loads(resume.parsed_content) if resume and resume.parsed_content else {}
        knowledge_base_context = interview.knowledge_base_snapshot or None

        messages_result = await db.execute(
            select(InterviewMessage)
            .where(InterviewMessage.interview_id == interview_id)
            .order_by(InterviewMessage.id)
        )
        messages = messages_result.scalars().all()
        chat_history = [{"role": item.role, "content": item.content} for item in messages]

        current_index = interview.current_question_index
        questions = InterviewService._serialize_questions(interview.questions_data or [])
        current_question_meta = dict(questions[current_index])
        current_question = current_question_meta["question"]

        candidate_msg = InterviewMessage(
            interview_id=interview_id,
            role="candidate",
            content=answer,
            question_index=current_index,
        )
        db.add(candidate_msg)

        evaluation_mode = interview.interview_mode
        try:
            if interview.interview_mode == "panel":
                evaluation = await AIService.evaluate_answer_with_panel(
                    question=current_question,
                    answer=answer,
                    resume_context=parsed_resume,
                    chat_history=chat_history,
                    knowledge_base=knowledge_base_context,
                    question_meta=current_question_meta,
                    panel_snapshot=interview.panel_snapshot,
                    ai_config=ai_config,
                )
            else:
                evaluation = await AIService.evaluate_answer(
                    question=current_question,
                    answer=answer,
                    resume_context=parsed_resume,
                    chat_history=chat_history,
                    knowledge_base=knowledge_base_context,
                    question_meta=current_question_meta,
                    ai_config=ai_config,
                )
        except Exception as exc:
            if interview.interview_mode != "panel":
                raise
            logger.warning("Panel evaluation failed, fallback to single mode: %s", exc)
            evaluation_mode = "single_fallback"
            evaluation = await AIService.evaluate_answer(
                question=current_question,
                answer=answer,
                resume_context=parsed_resume,
                chat_history=chat_history,
                knowledge_base=knowledge_base_context,
                question_meta=current_question_meta,
                ai_config=ai_config,
            )

        score = float(evaluation.get("score", 5.0))
        feedback = (evaluation.get("feedback") or "").strip()
        if not feedback:
            feedback = "本轮回答已记录，建议进一步补充关键细节和落地场景。"

        candidate_msg.score = Decimal(str(score))
        candidate_msg.feedback = feedback[:500]

        current_question_meta["used_slice_ids"] = (
            (evaluation.get("metadata") or {}).get("retrieved_slice_ids")
            or current_question_meta.get("used_slice_ids")
            or InterviewService._question_slice_ids(current_question_meta)
        )
        current_question_meta["evidence_trace"] = InterviewService._build_evidence_trace(
            current_question_meta.get("selected_slices") or [],
            used_slice_ids=current_question_meta.get("used_slice_ids") or [],
        )
        current_question_meta["evidence_summary"] = InterviewService._build_evidence_summary(
            current_question_meta.get("selected_slices") or [],
            used_slice_ids=current_question_meta.get("used_slice_ids") or [],
        )
        current_question_meta["selected_followups"] = (
            (evaluation.get("moderator") or {}).get("selected_followups")
            or evaluation.get("selected_followups")
            or current_question_meta.get("selected_followups")
            or []
        )
        if (evaluation.get("moderator") or {}).get("difficulty_hint"):
            current_question_meta["difficulty_hint"] = evaluation["moderator"]["difficulty_hint"]
        current_question_meta["answer"] = answer
        current_question_meta["score"] = score
        current_question_meta["feedback"] = feedback
        current_question_meta["evaluation"] = {
            **evaluation,
            "evaluation_mode": evaluation_mode,
        }
        questions[current_index] = current_question_meta

        next_index = current_index + 1
        is_finished = next_index >= interview.total_questions
        response = {
            "score": score,
            "feedback": feedback,
            "question_index": current_index,
            "is_finished": is_finished,
            "next_question": None,
            "evidence_summary": current_question_meta.get("evidence_summary") or [],
            "used_slice_ids": current_question_meta.get("used_slice_ids") or [],
        }

        if is_finished:
            interview.questions_data = InterviewService._serialize_questions(questions)
            interview.status = "completed"
            interview.current_question_index = next_index
            scored_values = [
                float(item.get("score"))
                for item in questions
                if item.get("score") is not None
            ]
            overall = round(sum(scored_values) / len(scored_values), 1) if scored_values else 0
            interview.overall_score = Decimal(str(overall))

            qa_data = InterviewService._build_qa_data(questions)
            report_signals = InterviewService._build_report_signals(questions)
            try:
                if interview.interview_mode == "panel":
                    report = await AIService.generate_panel_report(
                        parsed_resume=parsed_resume,
                        target_position=interview.target_position,
                        questions_and_scores=qa_data,
                        knowledge_base=knowledge_base_context,
                        panel_snapshot=interview.panel_snapshot,
                        report_signals=report_signals,
                        ai_config=ai_config,
                    )
                else:
                    report = await AIService.generate_report(
                        parsed_resume=parsed_resume,
                        target_position=interview.target_position,
                        questions_and_scores=qa_data,
                        knowledge_base=knowledge_base_context,
                        panel_snapshot=interview.panel_snapshot,
                        report_signals=report_signals,
                        ai_config=ai_config,
                    )
            except Exception as exc:
                logger.warning("Primary report generation failed, fallback to single report: %s", exc)
                report = await AIService.generate_report(
                    parsed_resume=parsed_resume,
                    target_position=interview.target_position,
                    questions_and_scores=qa_data,
                    knowledge_base=knowledge_base_context,
                    panel_snapshot=interview.panel_snapshot,
                    report_signals=report_signals,
                    ai_config=ai_config,
                )
                report["fallback_mode"] = "single_report_fallback"

            report = InterviewService._merge_report_defaults(
                report=report,
                report_signals=report_signals,
                interview_mode=interview.interview_mode,
            )
            report["question_scores"] = InterviewService._build_question_scores(questions)
            report["mode_label"] = (
                "内部多面试官协同 + 单主持人输出"
                if interview.interview_mode == "panel"
                else "单面试官模式"
            )
            interview.report = json.dumps(report, ensure_ascii=False)
        else:
            next_question_meta = dict(questions[next_index])
            if interview.interview_mode == "panel":
                next_question_meta = InterviewService._apply_followup_to_next_question(
                    current_question_meta=current_question_meta,
                    next_question_meta=next_question_meta,
                    evaluation=evaluation,
                )
            next_question_meta = InterviewService._reroute_question_slices(
                question_meta=next_question_meta,
                knowledge_base=knowledge_base_context,
                parsed_resume=parsed_resume,
                target_position=interview.target_position,
                difficulty=interview.difficulty,
                context_terms=InterviewService._extract_weakness_terms(current_question_meta, evaluation),
            )
            questions[next_index] = next_question_meta
            interview.questions_data = InterviewService._serialize_questions(questions)
            interview.current_question_index = next_index
            next_question = next_question_meta["question"]
            response["next_question"] = next_question
            db.add(
                InterviewMessage(
                    interview_id=interview_id,
                    role="interviewer",
                    content=next_question,
                    question_index=next_index,
                )
            )

        await db.commit()
        return response

    @staticmethod
    async def submit_answer_stream(
        db: AsyncSession,
        user_id: int,
        interview_id: int,
        answer: str,
        ai_config: Optional[Dict] = None,
    ):
        try:
            result = await InterviewService.submit_answer(
                db=db,
                user_id=user_id,
                interview_id=interview_id,
                answer=answer,
                ai_config=ai_config,
            )
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)}, ensure_ascii=False)}\n\n"
            return

        for chunk in InterviewService._chunk_text(result.get("feedback", "")):
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done', **result}, ensure_ascii=False)}\n\n"

    @staticmethod
    async def get_report(
        db: AsyncSession,
        user_id: int,
        interview_id: int,
    ) -> Dict:
        result = await db.execute(
            select(Interview).where(
                Interview.id == interview_id,
                Interview.user_id == user_id,
            )
        )
        interview = result.scalar_one_or_none()
        if not interview:
            raise NotFoundError(message="面试记录不存在")
        if interview.status != "completed":
            raise ValidationError(message="面试尚未完成")

        report = {}
        if interview.report:
            try:
                report = json.loads(interview.report)
            except json.JSONDecodeError:
                report = {}

        return {
            "interview_id": interview.id,
            "overall_score": float(interview.overall_score) if interview.overall_score else 0,
            "total_questions": interview.total_questions,
            "interview_mode": interview.interview_mode,
            "knowledge_base": interview.knowledge_base_snapshot,
            "panel_snapshot": interview.panel_snapshot,
            "report": report,
        }

    @staticmethod
    async def get_interviews(
        db: AsyncSession,
        user_id: int,
    ) -> Dict:
        result = await db.execute(
            select(Interview)
            .where(Interview.user_id == user_id)
            .order_by(Interview.created_at.desc())
        )
        interviews = result.scalars().all()
        items = [
            {
                "interview_id": item.id,
                "target_position": item.target_position,
                "difficulty": item.difficulty,
                "interview_mode": item.interview_mode or "single",
                "overall_score": float(item.overall_score) if item.overall_score else None,
                "total_questions": item.total_questions,
                "status": item.status,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in interviews
        ]
        return {"total": len(items), "items": items}

    @staticmethod
    async def get_interview_messages(
        db: AsyncSession,
        user_id: int,
        interview_id: int,
    ) -> List[Dict]:
        interview_result = await db.execute(
            select(Interview).where(
                Interview.id == interview_id,
                Interview.user_id == user_id,
            )
        )
        interview = interview_result.scalar_one_or_none()
        if not interview:
            raise NotFoundError(message="面试记录不存在")

        result = await db.execute(
            select(InterviewMessage)
            .where(InterviewMessage.interview_id == interview_id)
            .order_by(InterviewMessage.id)
        )
        messages = result.scalars().all()
        return [
            {
                "id": item.id,
                "role": item.role,
                "content": item.content,
                "question_index": item.question_index,
                "score": float(item.score) if item.score else None,
                "feedback": item.feedback,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in messages
        ]

    @staticmethod
    async def delete_interview(
        db: AsyncSession,
        user_id: int,
        interview_id: int,
    ) -> Dict:
        result = await db.execute(
            select(Interview).where(
                Interview.id == interview_id,
                Interview.user_id == user_id,
            )
        )
        interview = result.scalar_one_or_none()
        if not interview:
            raise NotFoundError(message="面试记录不存在")

        await db.execute(
            sql_delete(InterviewMessage).where(InterviewMessage.interview_id == interview_id)
        )
        await db.delete(interview)
        await db.commit()
        return {"message": "面试记录已删除"}

    @staticmethod
    async def delete_interview_admin(
        db: AsyncSession,
        interview_id: int,
    ) -> Dict:
        interview = await db.get(Interview, interview_id)
        if not interview:
            raise NotFoundError(message="面试记录不存在")

        await db.execute(
            sql_delete(InterviewMessage).where(InterviewMessage.interview_id == interview_id)
        )
        await db.delete(interview)
        await db.commit()
        return {"message": "面试记录已删除"}


interview_service = InterviewService()
