import pytest

from app.services.client.ai_service import AIService, PANEL_OUTPUT_VERSION


def _panel_snapshot():
    return {
        "mode": "panel",
        "roles": [
            {
                "key": "technical_deep_dive",
                "name": "Technical Deep Dive",
                "focus": "Probe engineering trade-offs.",
            },
            {
                "key": "project_follow_up",
                "name": "Project Follow-up",
                "focus": "Verify ownership and delivery.",
            },
            {
                "key": "behavior_expression",
                "name": "Behavior & Communication",
                "focus": "Evaluate clarity and communication.",
            },
        ],
    }


@pytest.mark.unit
def test_normalize_panel_question_payload_keeps_structured_contract():
    payload = {
        "panel": [
            {
                "role": "technical",
                "role_key": "technical_deep_dive",
                "focus": "Probe engineering trade-offs.",
                "question_candidates": ["How did you design the cache strategy?"],
                "followup_candidates": ["What broke under pressure?"],
                "evaluation_points": ["technical depth", "trade-offs"],
            }
        ],
        "moderator": {
            "selected_questions": [
                {
                    "index": 0,
                    "selected_question": "Please walk through the cache strategy you designed.",
                    "selected_followups": ["What trade-offs did you accept?"],
                    "reasoning_summary": "Best opening for technical depth.",
                    "lead_role": "technical_deep_dive",
                    "support_roles": ["project_follow_up"],
                    "evaluation_points": ["technical depth", "trade-offs"],
                    "used_slice_ids": [11, 12],
                }
            ],
            "feedback_style": "firm but constructive",
            "difficulty_hint": "medium",
            "reasoning_summary": "Start with the strongest technical thread.",
        },
        "metadata": {
            "mode": "panel",
            "version": PANEL_OUTPUT_VERSION,
            "retrieved_slice_ids": [11, 12],
            "fallback_allowed": True,
        },
    }
    question_plan = [
        {
            "index": 0,
            "stage": "technical",
            "category": "technical",
            "lead_role": "technical_deep_dive",
            "support_roles": ["project_follow_up"],
            "intent": "Validate technical depth.",
            "evaluation_focus": ["technical depth"],
            "selected_slices": [{"slice_id": 11}, {"slice_id": 12}],
        }
    ]

    normalized = AIService._normalize_panel_question_payload(
        payload=payload,
        question_plan=question_plan,
        knowledge_base={"slices": [{"slice_id": 11}, {"slice_id": 12}]},
        panel_snapshot=_panel_snapshot(),
    )

    assert normalized["metadata"]["version"] == PANEL_OUTPUT_VERSION
    assert normalized["questions"][0]["question"] == "Please walk through the cache strategy you designed."
    assert normalized["questions"][0]["selected_followups"] == ["What trade-offs did you accept?"]
    assert normalized["questions"][0]["panel_context"]["metadata"]["retrieved_slice_ids"] == [11, 12]


@pytest.mark.unit
def test_normalize_panel_evaluation_payload_keeps_single_moderator_output():
    payload = {
        "panel": [
            {
                "role": "technical",
                "role_key": "technical_deep_dive",
                "focus": "Probe engineering trade-offs.",
                "followup_candidates": ["What would you optimize next?"],
                "evaluation_points": ["root cause depth", "trade-off clarity"],
            }
        ],
        "moderator": {
            "score": 8.2,
            "feedback": "Good depth, but quantify the trade-offs more clearly.",
            "follow_up": True,
            "next_focus": "Explain capacity planning.",
            "selected_followups": ["How did you estimate capacity?"],
            "reasoning_summary": "Strong answer with one missing trade-off detail.",
            "difficulty_hint": "medium",
        },
        "metadata": {
            "mode": "panel",
            "version": PANEL_OUTPUT_VERSION,
            "retrieved_slice_ids": [21],
            "fallback_allowed": True,
        },
        "strengths": ["Clear root cause analysis"],
        "gaps": ["Trade-off quantification"],
    }
    question_meta = {
        "question": "How did you debug the cache failure?",
        "lead_role": "technical_deep_dive",
        "evaluation_focus": ["root cause depth"],
        "selected_slices": [{"slice_id": 21}],
    }

    normalized = AIService._normalize_panel_evaluation_payload(
        payload=payload,
        question_meta=question_meta,
        knowledge_base={"slices": [{"slice_id": 21}]},
        panel_snapshot=_panel_snapshot(),
    )

    assert normalized["score"] == 8.2
    assert normalized["feedback"] == "Good depth, but quantify the trade-offs more clearly."
    assert normalized["moderator"]["selected_followups"] == ["How did you estimate capacity?"]
    assert normalized["metadata"]["retrieved_slice_ids"] == [21]
