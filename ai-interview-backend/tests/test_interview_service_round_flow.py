import pytest

from app.services.client.ai_service import AIService
from app.services.client.interview_service import InterviewService


@pytest.mark.unit
def test_apply_followup_to_next_question_rewrites_next_round_with_moderator_choice():
    current_question_meta = {
        "index": 1,
        "question": "Tell me about the cache architecture.",
        "intent": "Assess system design depth.",
        "question_target_gap": "Trade-off clarity",
        "question_target_evidence": ["Cache degradation design evidence"],
        "question_target_evidence_ids": [21],
        "panel_context": {
            "moderator": {
                "selected_question": "Tell me about the cache architecture.",
                "selected_followups": [],
            }
        },
    }
    next_question_meta = {
        "index": 2,
        "question": "Original next question",
        "intent": "Assess trade-offs.",
        "evaluation_focus": ["trade-offs"],
        "category": "technical_depth",
    }
    evaluation = {
        "gaps": ["trade-off clarity"],
        "next_focus": "Explain failover and degradation.",
        "moderator": {
            "selected_followups": [
                "If Redis is unavailable, how do you degrade gracefully?",
                "What metrics would you watch first?",
            ],
            "next_best_followup": {
                "question": "If Redis is unavailable, how do you degrade gracefully?",
                "target_gap": "Trade-off clarity",
                "target_evidence": ["Cache degradation design evidence"],
                "evidence_source_ids": [21],
                "evidence_source_summary": ["Architecture slice matched degradation strategy"],
                "reason": "Need to verify whether the candidate can explain the degradation decision in concrete terms.",
            },
            "reasoning_summary": "Continue the strongest thread with a tighter follow-up.",
            "difficulty_hint": "medium",
        },
    }

    rewritten = InterviewService._apply_followup_to_next_question(
        current_question_meta=current_question_meta,
        next_question_meta=next_question_meta,
        evaluation=evaluation,
    )

    assert rewritten["question"] == "If Redis is unavailable, how do you degrade gracefully?"
    assert rewritten["selected_followups"] == ["What metrics would you watch first?"]
    assert rewritten["followup_source_question_index"] == 1
    assert rewritten["is_dynamic_followup"] is True
    assert rewritten["intent"] == "Explain failover and degradation."
    assert rewritten["evaluation_focus"] == ["trade-off clarity"]
    assert rewritten["question_target_gap"] == "Trade-off clarity"
    assert rewritten["question_target_evidence"] == ["Cache degradation design evidence"]
    assert rewritten["question_target_evidence_ids"] == [21]
    assert rewritten["question_reason"] == "Need to verify whether the candidate can explain the degradation decision in concrete terms."
    assert rewritten["panel_context"]["moderator"]["next_best_followup"]["evidence_source_ids"] == [21]
    assert rewritten["panel_context"]["moderator"]["selected_question"] == rewritten["question"]


@pytest.mark.unit
def test_reroute_question_slices_and_report_signals_capture_round_metadata():
    question_meta = {
        "index": 1,
        "question": "How would you design the cache and database access path?",
        "stage": "technical",
        "lead_role": "technical_deep_dive",
        "category": "technical_depth",
        "intent": "Probe technical depth.",
        "evaluation_focus": ["system design", "trade-offs"],
    }
    knowledge_base = {
        "slices": [
            {
                "slice_id": 11,
                "title": "High concurrency cache design",
                "content": "Focus on cache breakdown, graceful degradation, SQL hotspots, and Redis trade-offs.",
                "priority": 9,
                "stage_tags": ["technical", "scenario"],
                "role_tags": ["technical_deep_dive"],
                "scene_tags": ["technical_depth", "pressure_case"],
                "topic_tags": ["Python Backend Engineer", "system_design"],
                "skill_tags": ["fastapi", "redis", "postgres"],
                "keywords": ["cache_breakdown", "sql_hotspot", "graceful_degradation"],
                "source_section": "focus_points",
                "difficulty": "medium",
                "is_enabled": True,
            },
            {
                "slice_id": 12,
                "title": "Communication basics",
                "content": "Focus on self-introduction and communication structure.",
                "priority": 3,
                "stage_tags": ["opening"],
                "role_tags": ["behavior_expression"],
                "scene_tags": ["self_intro"],
                "topic_tags": ["communication"],
                "skill_tags": [],
                "keywords": ["communication"],
                "source_section": "overview",
                "difficulty": "easy",
                "is_enabled": True,
            },
        ]
    }
    parsed_resume = {
        "skills": ["fastapi", "redis"],
        "projects": ["cache platform", "task scheduler"],
    }

    routed = InterviewService._reroute_question_slices(
        question_meta=question_meta,
        knowledge_base=knowledge_base,
        parsed_resume=parsed_resume,
        target_position="Python Backend Engineer",
        difficulty="medium",
        context_terms=["graceful degradation", "sql hotspot"],
    )

    selected_ids = [item["slice_id"] for item in routed["selected_slices"]]
    assert selected_ids[0] == 11
    assert 11 in selected_ids
    assert 11 in routed["used_slice_ids"]
    assert 11 in routed["panel_context"]["metadata"]["retrieved_slice_ids"]
    assert routed["evidence_summary"]
    assert routed["evidence_trace"]
    assert routed["evidence_trace"][0]["reason_summary"]

    questions = [
        {
            **routed,
            "evaluation": {
                "gaps": ["trade-off clarity", "trade-off clarity"],
                "unresolved_gaps": ["trade-off clarity"],
                "strengths": ["technical depth"],
                "next_focus": "quantify degradation strategy",
                "evidence_strength_delta": [
                    {
                        "evidence": "Cache degradation design evidence",
                        "delta": "strengthened",
                        "reason": "The answer clarified the degradation sequence.",
                    }
                ],
                "claim_confidence_change": [
                    {
                        "claim": "Led the cache redesign",
                        "from_level": "medium",
                        "to_level": "high",
                        "change": "increased",
                        "reason": "The answer added direct ownership details.",
                    }
                ],
                "next_best_followup": {
                    "question": "How did you quantify the degradation budget?",
                    "target_gap": "trade-off clarity",
                    "reason": "Need one more concrete metric for the degradation path.",
                },
                "panel_views": [
                    {"role": "technical_deep_dive", "summary": "Strong architecture depth."},
                    {"role": "project_follow_up", "summary": "Need clearer ownership boundaries."},
                ],
            },
        },
        {
            "question": "How did you coordinate rollout?",
            "used_slice_ids": [11, 15],
            "evaluation": {
                "gaps": ["ownership clarity"],
                "unresolved_gaps": ["ownership clarity"],
                "strengths": ["clear communication"],
                "next_focus": "describe rollout metrics",
                "evidence_strength_delta": [
                    {
                        "evidence": "Rollout ownership evidence",
                        "delta": "insufficient",
                        "reason": "The answer still lacked measurable rollout ownership.",
                    }
                ],
                "next_best_followup": {
                    "question": "Which rollout metrics did you personally monitor?",
                    "target_gap": "ownership clarity",
                    "reason": "Need direct proof of operational ownership.",
                },
                "panel_views": [
                    {"role": "project_follow_up", "summary": "Need clearer ownership boundaries."}
                ],
            },
        },
    ]

    report_signals = InterviewService._build_report_signals(questions)
    merged_report = InterviewService._merge_report_defaults({}, report_signals, "panel")

    assert report_signals["common_gaps"][0] == "trade-off clarity"
    assert report_signals["retrieved_slice_ids"][0] == 11
    assert set(report_signals["retrieved_slice_ids"]) == {11, 12, 15}
    assert "quantify degradation strategy" in report_signals["training_priorities"]
    assert "trade-off clarity" in report_signals["training_priorities"]
    assert any(item["role"] == "technical_deep_dive" for item in report_signals["panel_summary"])
    assert report_signals["common_strengths"][0] == "technical depth"
    assert report_signals["evidence_summary"]
    assert report_signals["followup_loop_summary"]
    assert report_signals["claim_confidence_summary"]
    assert merged_report["evidence_summary"] == report_signals["evidence_summary"]
    assert merged_report["common_gaps"] == report_signals["common_gaps"]
    assert merged_report["common_strengths"] == report_signals["common_strengths"]
    assert merged_report["followup_loop_summary"] == report_signals["followup_loop_summary"]
    assert merged_report["claim_confidence_summary"] == report_signals["claim_confidence_summary"]
    assert merged_report["panel_summary"] == report_signals["panel_summary"]


@pytest.mark.unit
def test_apply_blueprint_to_question_plan_adds_track_and_traceable_fields():
    question_plan = [
        {
            "index": 0,
            "question": "Please introduce yourself.",
            "stage": "opening",
            "category": "self-intro",
            "intent": "Assess fit.",
            "evaluation_focus": ["communication"],
            "selected_followups": [],
        },
        {
            "index": 1,
            "question": "Tell me about your core project.",
            "stage": "project",
            "category": "project",
            "intent": "Assess ownership.",
            "evaluation_focus": ["ownership"],
            "selected_followups": [],
        },
    ]
    blueprint = {
        "training_focus": ["Clarify ownership boundaries", "Quantify trade-offs"],
        "high_risk_claims": [{"claim": "Led a platform rebuild"}],
        "priority_question_tracks": [
            {
                "track": "Project ownership verification",
                "reason": "Need to verify whether the rebuild was led or supported by the candidate",
                "requirement_status": "weak",
                "evidence_ids": [31, 32],
            }
        ],
        "blueprint_evidence": {
            "slice_ids": [31, 32],
            "slice_summaries": ["Architecture slice matched project depth"],
        },
        "evidence_summary": ["Weak support around rebuild ownership"],
    }

    enriched = InterviewService._apply_blueprint_to_question_plan(question_plan, blueprint)

    assert enriched[0]["blueprint_track"] == "Project ownership verification"
    assert enriched[0]["blueprint_requirement_status"] == "weak"
    assert enriched[0]["blueprint_evidence_ids"] == [31, 32]
    assert enriched[0]["blueprint_evidence_summary"]
    assert "Project ownership verification" in enriched[0]["intent"]
    assert "Led a platform rebuild" in enriched[0]["selected_followups"]


@pytest.mark.asyncio
async def test_evaluate_round_falls_back_to_single_when_panel_evaluation_fails(monkeypatch):
    async def _raise_panel(**kwargs):
        raise RuntimeError("panel failed")

    async def _single_eval(**kwargs):
        return {
            "score": 6.5,
            "feedback": "Need more concrete ownership evidence.",
            "unresolved_gaps": ["ownership clarity"],
            "next_best_followup": {
                "question": "Which decisions were made by you personally?",
                "target_gap": "ownership clarity",
                "evidence_source_ids": [31],
            },
        }

    monkeypatch.setattr(AIService, "evaluate_answer_with_panel", _raise_panel)
    monkeypatch.setattr(AIService, "evaluate_answer", _single_eval)

    mode, evaluation = await InterviewService._evaluate_round(
        interview_mode="panel",
        question="Tell me about the migration project.",
        answer="I helped drive the migration.",
        resume_context={},
        chat_history=[],
        knowledge_base=None,
        question_meta={"question_target_gap": "ownership clarity", "question_target_evidence_ids": [31]},
        panel_snapshot={"mode": "panel"},
        ai_config=None,
    )

    assert mode == "single_fallback"
    assert evaluation["feedback"] == "Need more concrete ownership evidence."
    assert evaluation["next_best_followup"]["target_gap"] == "ownership clarity"
