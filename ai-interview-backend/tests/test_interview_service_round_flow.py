import pytest

from app.services.client.interview_service import InterviewService


@pytest.mark.unit
def test_apply_followup_to_next_question_rewrites_next_round_with_moderator_choice():
    current_question_meta = {
        "index": 1,
        "question": "Tell me about the cache architecture.",
        "intent": "Assess system design depth.",
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

    questions = [
        {
            **routed,
            "evaluation": {
                "gaps": ["trade-off clarity", "trade-off clarity"],
                "strengths": ["technical depth"],
                "next_focus": "quantify degradation strategy",
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
                "strengths": ["clear communication"],
                "next_focus": "describe rollout metrics",
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
    assert any(item["role"] == "technical_deep_dive" for item in report_signals["panel_summary"])
    assert merged_report["common_gaps"] == report_signals["common_gaps"]
    assert merged_report["panel_summary"] == report_signals["panel_summary"]
