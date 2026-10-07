"""Build the focused parallel EN/TH dataset.

Run from the workspace root::

    python -m decision_models.tools.build_focused

Authorship lives here rather than in the JSONL because *parallelism is the
experiment*. Every item is written once, in both languages, sharing one
question schema and one expected label; generating the rows from a single table
makes it impossible for the Thai side to drift into a different task from the
English side. The emitted JSONL is committed alongside this script so a run can
be reproduced without re-running the builder.

Rules for holding the gold label honest:

* **routing / triage / noul** -- the label follows directly from what the state
  states, so no model judgement is needed to write it down.
* **score** -- the level is named in the state ("angry, caps, threat to
  cancel" -> the top level), so the target is the model's reading, not a
  taste call.
* **budget/cardinality items (18-way)** -- the gold is the *inverse* of the
  last move named in the state, under a rule the state states in full. Small
  reasoning, provable answer, high option count.
* **placement (4-way)** -- candidates are given as explicit feature rows and
  the state states the selection rule ("fewest holes, then lowest max height"),
  so the answer is arithmetic on the stated numbers rather than a Tetris
  aesthetic.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "data", "focused_items.jsonl")

# --------------------------------------------------------------------- question schemas

ROUTE_Q = {
    "route": {
        "type": "choice",
        "instructions": "Which subagent should handle this request?",
        "criteria": {
            "reservation": "Booking, modifying, cancelling, or questions about a rental reservation or pick-up",
            "weather": "Weather, forecast, rain, snow, or climate for the trip or destination",
            "cost": "Pricing, total cost, budget, fees, or cost comparison",
            "general": "Anything else, or a greeting or general question about the service",
        },
    }
}

TRIAGE_Q = {
    "department": {
        "type": "choice",
        "instructions": "Which department should handle this request?",
        "criteria": {
            "billing": "invoices, payments, refunds, duplicate charges",
            "technical": "bugs, outages, crashes, login failures, error messages",
            "sales": "pricing plans, upgrades, new contracts, feature questions",
            "other": "everything else",
        },
    }
}

TRIAGE_FULL_Q = {
    "department": TRIAGE_Q["department"],
    "urgency": {
        "type": "score",
        "instructions": "How urgent is this request?",
        "criteria": ["not urgent", "soon", "critical deadline or blocking issue"],
    },
    "refund_requested": {
        "type": "noul",
        "instructions": "Does the user explicitly request a refund?",
    },
}

FRUSTRATION_Q = {
    "frustration": {
        "type": "score",
        "instructions": "How frustrated is the customer?",
        "criteria": ["calm", "mildly annoyed", "angry"],
    }
}

FRUSTRATION5_Q = {
    "frustration": {
        "type": "score",
        "instructions": "How frustrated is the customer?",
        "criteria": ["calm", "slightly annoyed", "annoyed", "angry", "furious"],
    }
}

CHURN_Q = {
    "churn_threat": {
        "type": "noul",
        "instructions": "Does the user threaten to cancel or leave?",
    }
}

# The 18 standard face turns, written the way the cube app names them.
CUBE_MOVES = ["R", "R'", "R2", "L", "L'", "L2", "U", "U'", "U2",
              "D", "D'", "D2", "F", "F'", "F2", "B", "B'", "B2"]
CUBE_Q = {
    "next_move": {
        "type": "choice",
        "instructions": "Which move should be applied next?",
        "criteria": {m: "rotate: %s" % m for m in CUBE_MOVES},
    }
}

PLACEMENT_Q = {
    "placement": {
        "type": "choice",
        "instructions": "Which placement should the piece be dropped into?",
        "criteria": {
            "opt_0": "candidate A",
            "opt_1": "candidate B",
            "opt_2": "candidate C",
            "opt_3": "candidate D",
        },
    },
    "safe": {
        "type": "noul",
        "instructions": "Does the chosen placement avoid creating any new holes?",
    },
}


def cube_state(last_move: str, inverse_en: str, inverse_th: str) -> Dict[str, str]:
    """An 18-way choice whose answer is the inverse of the move named in the state."""
    return {
        "en": (
            "Rubik's Cube 3x3, beginner method, undo step. The solver just applied the move %s "
            "and must now undo it. The rule for this step, stated in full: the inverse of R is R', "
            "the inverse of R' is R, and the inverse of any 180-degree turn (X2) is itself. "
            "Last move applied: %s." % (last_move, last_move)
        ),
        "th": (
            "ลูกบาศก์รูบิค 3x3 วิธีเริ่มต้น ขั้นย้อนกลับ ตัวแก้เพิ่งหมุน %s และต้องย้อนกลับ "
            "กฎของขั้นนี้ระบุไว้ครบแล้ว: ตัวผกผันของ R คือ R' ตัวผกผันของ R' คือ R "
            "และตัวผกผันของกลม 180 องศา (X2) คือตัวมันเอง การหมุนครั้งล่าสุด: %s" % (last_move, last_move)
        ),
    }


PLACEMENT_RULE_EN = (
    "Selection rule, stated in full: choose the candidate with the fewest holes; if two tie on "
    "holes, choose the lower maximum height. Candidate features -- "
)
PLACEMENT_RULE_TH = (
    "กฎการเลือก ระบุไว้ครบแล้ว: เลือกตัวเลือกที่มีจำนวนรูน้อยที่สุด ถ้าเท่ากันให้เลือกตัวที่ความสูงสูงสุดต่ำกว่า "
    "คุณสมบัติของแต่ละตัวเลือก -- "
)


# --------------------------------------------------------------------- the item table
# Each entry: id, family, en, th, questions, expected, tags.
# `expected` is keyed by question id and is shared by both languages: that is the
# parallelism claim, and a per-language difference here would mean the two rows
# are not the same task.

ITEMS: List[Dict[str, Any]] = [
    # ---- routing: mirrors Route_gate/src/__tests__/supervisor.test.ts
    dict(id="route-weather-01", family="routing", questions=ROUTE_Q, expected={"route": "weather"},
         en="Will it rain in Lisbon next Tuesday?",
         th="วันอังคารหน้าฝนจะตกที่ลิสบอนไหม"),
    dict(id="route-reservation-01", family="routing", questions=ROUTE_Q, expected={"route": "reservation"},
         en="Please reserve a car for next week in Paris",
         th="ช่วยจองรถให้หน่อยสำหรับสัปดาห์หน้าที่ปารีส"),
    dict(id="route-cost-01", family="routing", questions=ROUTE_Q, expected={"route": "cost"},
         en="How much does a 5-day SUV rental cost?",
         th="ค่าเช่ารถ SUV ห้าวันราคาเท่าไหร่"),
    dict(id="route-general-01", family="routing", questions=ROUTE_Q, expected={"route": "general"},
         en="Hi there, what do you do?",
         th="สวัสดีครับ คุณให้บริการอะไรบ้าง"),
    dict(id="route-ambiguous-01", family="routing", questions=ROUTE_Q, expected={"route": "reservation"},
         en="I want to cancel my reservation, how much is the cancellation fee?",
         th="อยาก cancel การจอง อยากรู้ว่าค่าธรรมเนียมการยกเลิกเท่าไหร่"),  # mixed Thai/English on purpose
    dict(id="route-weather-02", family="routing", questions=ROUTE_Q, expected={"route": "weather"},
         en="Is it going to snow at the destination this weekend?",
         th="สุดสัปดาห์นี้ที่จุดหมายปลายทางหิมะจะตกไหม"),
    dict(id="route-cost-02", family="routing", questions=ROUTE_Q, expected={"route": "cost"},
         en="Can you compare the total cost of the two packages for me? It is over my budget.",
         th="ช่วยเทียบราคารวมของทั้งสองแพ็กเกจให้หน่อย เกินงบประมาณของฉัน"),
    dict(id="route-reservation-02", family="routing", questions=ROUTE_Q, expected={"route": "reservation"},
         en="I need to change the pick-up time on my existing booking.",
         th="ฉันต้องการเปลี่ยนเวลารับรถในการจองที่มีอยู่แล้ว"),
    # ---- triage: the same shape OpenThai's own card demonstrates
    dict(id="triage-billing-01", family="triage", questions=TRIAGE_Q, expected={"department": "billing"},
         en="I was charged twice for March. Please refund the duplicate charge.",
         th="โดนหักเงินซ้ำสองครั้งในเดือนมีนาคม ขอเงินคืนรายการซ้ำด้วย"),
    dict(id="triage-technical-01", family="triage", questions=TRIAGE_Q, expected={"department": "technical"},
         en="The app crashes with a stack trace every time I open settings.",
         th="แอปค้างและขึ้น error ทุกครั้งที่เปิดหน้าตั้งค่า"),
    dict(id="triage-sales-01", family="triage", questions=TRIAGE_Q, expected={"department": "sales"},
         en="What does the enterprise plan cost and can we upgrade mid-contract?",
         th="แพ็กเกจองค์กรราคาเท่าไหร่ และอัปเกรดกลางสัญญาได้ไหม"),
    dict(id="triage-other-01", family="triage", questions=TRIAGE_Q, expected={"department": "other"},
         en="Thanks, the courier already arrived. Have a nice day.",
         th="ขอบคุณครับ พนักงานส่งของมาถึงแล้ว ขอให้เป็นวันที่ดี"),
    dict(id="triage-billing-02", family="triage", questions=TRIAGE_Q, expected={"department": "billing"},
         en="Where can I download the invoice for last month? I cannot find the payment receipt.",
         th="ดาวน์โหลดใบแจ้งหนี้ของเดือนที่แล้วได้ที่ไหน หาใบเสร็จการชำระเงินไม่เจอ"),
    # ---- triage with all three primitives at once
    dict(id="multi-billing-refund-01", family="multi", questions=TRIAGE_FULL_Q,
         expected={"department": "billing", "urgency": 2, "refund_requested": True},
         en="We were billed twice in March and nobody has answered in three days. Refund the duplicate today or we cancel.",
         th="ถูกเรียกเก็บเงินซ้ำในเดือนมีนาคม สามวันแล้วไม่มีใครตอบ ขอเงินคืนวันนี้เลยไม่งั้นขอยกเลิก"),
    dict(id="multi-technical-01", family="multi", questions=TRIAGE_FULL_Q,
         expected={"department": "technical", "urgency": 1, "refund_requested": False},
         en="Login fails intermittently for some users. Not blocking yet, but it is getting worse.",
         th="การเข้าสู่ระบบล้มเหลวเป็นครั้งคราวกับผู้ใช้บางคน ยังไม่ถึงขั้นบล็อกงาน แต่แย่ลงเรื่อย ๆ"),
    dict(id="multi-sales-01", family="multi", questions=TRIAGE_FULL_Q,
         expected={"department": "sales", "urgency": 0, "refund_requested": False},
         en="Just curious what the roadmap looks like for next year, no rush at all.",
         th="แค่อยากรู้ว่าแผนงานปีหน้าจะเป็นอย่างไร ไม่รีบเลย"),
    dict(id="multi-billing-01", family="multi", questions=TRIAGE_FULL_Q,
         expected={"department": "billing", "urgency": 2, "refund_requested": False},
         en="Our card was declined and the account is locked right now. We cannot process any orders.",
         th="บัตรของเราถูกปฏิเสธและบัญชีถูกล็อกอยู่ตอนนี้ เราประมวลผลออเดอร์ไม่ได้เลย"),
    # ---- noul
    dict(id="noul-churn-01", family="noul", questions=CHURN_Q, expected={"churn_threat": True},
         en="Fix this today or we will cancel our plan and move to a competitor.",
         th="แก้ไขวันนี้ ไม่งั้นเราจะยกเลิกแผนและย้ายไปใช้เจ้าอื่น"),
    dict(id="noul-churn-02", family="noul", questions=CHURN_Q, expected={"churn_threat": False},
         en="Everything works well now, thank you for the quick fix.",
         th="ตอนนี้ใช้งานได้ดีแล้ว ขอบคุณที่แก้ไขให้เร็ว"),
    dict(id="noul-churn-03", family="noul", questions=CHURN_Q, expected={"churn_threat": True},
         en="If this is not resolved by Friday we are leaving.",
         th="ถ้าภายในวันศุกร์ยังไม่จบ เราจะเลิกใช้"),
    dict(id="noul-churn-04", family="noul", questions=CHURN_Q, expected={"churn_threat": False},
         en="Is there a way to export my data as CSV?",
         th="มีวิธีส่งออกข้อมูลของฉันเป็น CSV ไหม"),
    # ---- score
    dict(id="score-frustration-01", family="score", questions=FRUSTRATION_Q, expected={"frustration": 2},
         en="This is the THIRD time I have written about this!! Nobody responds!! Absolutely unacceptable!!!",
         th="นี่เป็นครั้งที่สามแล้วที่ฉันเขียนเรื่องนี้!! ไม่มีใครตอบเลย!! ยอมรับไม่ได้จริง ๆ!!!"),
    dict(id="score-frustration-02", family="score", questions=FRUSTRATION_Q, expected={"frustration": 0},
         en="Hello, whenever you have a moment, could you let me know if the invoice was received?",
         th="สวัสดีครับ เมื่อคุณสะดวก ช่วยแจ้งให้ทราบว่าได้รับใบแจ้งหนี้แล้วหรือไม่"),
    dict(id="score-frustration-03", family="score", questions=FRUSTRATION_Q, expected={"frustration": 1},
         en="It still does not work, I already tried restarting twice.",
         th="ยังใช้ไม่ได้อยู่ดี ฉันลองรีสตาร์ทไปสองรอบแล้ว"),
    dict(id="score-frustration-04", family="score", questions=FRUSTRATION5_Q, expected={"frustration": 4},
         en="I am furious. This has cost my team an entire day and I want it escalated immediately.",
         th="ฉันโมโหสุด ๆ แล้ว มันทำทีมของฉันเสียเวลาทั้งวัน ต้องการให้ส่งเรื่องต่อทันที"),
    dict(id="score-frustration-05", family="score", questions=FRUSTRATION5_Q, expected={"frustration": 1},
         en="Minor thing: the font in the report header is slightly off. Low priority.",
         th="เรื่องเล็กน้อย ฟอนต์ในหัวรายงานเพี้ยนนิดหน่อย ไม่เร่งด่วน"),
    # ---- high cardinality: 18-way choice
    dict(id="cube-inverse-01", family="cardinality18", questions=CUBE_Q, expected={"next_move": "U'"},
         **cube_state("U", "U'", "U'")),
    dict(id="cube-inverse-02", family="cardinality18", questions=CUBE_Q, expected={"next_move": "F"},
         **cube_state("F'", "F", "F")),
    dict(id="cube-inverse-03", family="cardinality18", questions=CUBE_Q, expected={"next_move": "L2"},
         **cube_state("L2", "L2", "L2")),
    # ---- 4-way placement with an arithmetic gold
    dict(id="placement-01", family="cardinality4", questions=PLACEMENT_Q,
         expected={"placement": "opt_2", "safe": True},
         en=PLACEMENT_RULE_EN + "A: 2 holes, max height 7. B: 3 holes, max height 5. C: 1 hole, max height 6. D: 1 hole, max height 8.",
         th=PLACEMENT_RULE_TH + "A: 2 รู สูงสุด 7. B: 3 รู สูงสุด 5. C: 1 รู สูงสุด 6. D: 1 รู สูงสุด 8."),
    dict(id="placement-02", family="cardinality4", questions=PLACEMENT_Q,
         expected={"placement": "opt_0", "safe": True},
         en=PLACEMENT_RULE_EN + "A: 0 holes, max height 9. B: 0 holes, max height 12. C: 1 hole, max height 4. D: 2 holes, max height 3.",
         th=PLACEMENT_RULE_TH + "A: 0 รู สูงสุด 9. B: 0 รู สูงสุด 12. C: 1 รู สูงสุด 4. D: 2 รู สูงสุด 3."),
    dict(id="placement-03", family="cardinality4", questions=PLACEMENT_Q,
         expected={"placement": "opt_1", "safe": False},
         en=PLACEMENT_RULE_EN + "A: 2 holes, max height 6. B: 1 hole, max height 11. C: 2 holes, max height 5. D: 3 holes, max height 4.",
         th=PLACEMENT_RULE_TH + "A: 2 รู สูงสุด 6. B: 1 รู สูงสุด 11. C: 2 รู สูงสุด 5. D: 3 รู สูงสุด 4."),
    # ---- Thai-only registers: no English row to pair with, by construction
    dict(id="thai-register-01", family="thai-only", questions=CHURN_Q, expected={"churn_threat": True},
         th="ยังไงก็ได้นะ แต่ถ้าไม่จบภายในสิ้นเดือนนี้ก็คงต้องหาที่ใหม่ล่ะ",
         en=None),
    dict(id="thai-register-02", family="thai-only", questions=TRIAGE_Q, expected={"department": "technical"},
         th="ระบบค้าง ไม่ยอมโหลดเลยค่ะ ลองรีเฟรชแล้วก็ยังเงียบ",
         en=None),
    dict(id="thai-register-03", family="thai-only", questions=FRUSTRATION_Q, expected={"frustration": 2},
         th="ทำไมเรื่องแค่นี้ต้องให้ตามสามรอบวะ ทำงานกันยังไงเนี่ย",
         en=None),
    dict(id="thai-register-04", family="thai-only", questions=TRIAGE_Q, expected={"department": "billing"},
         th="ยอดในใบกำกับภาษีไม่ตรงกับที่โอนไปนะครับ รบกวนตรวจสอบให้ด้วยครับ",
         en=None),
]


def build() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for item in ITEMS:
        if item["id"] in seen:
            raise ValueError("duplicate item id %r" % item["id"])
        seen.add(item["id"])
        for lang, key in (("en", "en"), ("th", "th")):
            text = item.get(key)
            if not text:
                continue
            rows.append({
                "id": item["id"],
                "state": text,
                "questions": item["questions"],
                "expected": item["expected"],
                "language": lang,
                "tags": [item["id"], item["family"], lang],
                "family": item["family"],
            })
    return rows


def main() -> None:
    rows = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")
    families: Dict[str, int] = {}
    languages: Dict[str, int] = {}
    for row in rows:
        families[row["family"]] = families.get(row["family"], 0) + 1
        languages[row["language"]] = languages.get(row["language"], 0) + 1
    print("wrote %d rows to %s" % (len(rows), OUT))
    print("by family:", dict(sorted(families.items())))
    print("by language:", languages)


if __name__ == "__main__":
    main()
