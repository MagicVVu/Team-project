"""Forty six-turn scenarios, isolated by ten semantic scenario families."""
import json
from pathlib import Path

FOLLOWUPS = ["接着之前的牛奶，它现在还剩多少，在哪", "回到最开始查过的那个，现在在哪", "前面提到的牛奶，现在的数量和位置呢", "我们继续刚开始聊的牛奶，还有多少，放哪了"]
SOCIAL = ["我今天整理得好累，怎么收拾能省心点", "家里的东西总是找不到，我有点烦", "先聊会儿，整理厨房从哪里开始比较轻松", "你好，今天想慢慢收拾一下家里"]


def scenarios():
    rows = []
    for group in range(1, 11):
        for variant in range(4):
            action = "MOVE" if group == 9 else "OPEN" if group == 10 else "CONSUME"
            followup = FOLLOWUPS[variant]
            if group == 4: followup = "回到最开始查过的那个，现在在哪"
            third = "把它移到厨房" if action == "MOVE" else "它昨天开封，帮我记一下" if action == "OPEN" else "我喝了一半，帮我记一下"
            fourth = "还是挪到储物柜吧" if action == "MOVE" else "说错了，应该是今天开封" if action == "OPEN" else "还是两盒吧"
            if group == 7:
                third, fourth = "如果我喝掉一半会怎么样，我只是问问", "请帮我登记消耗两盒"
            if group == 8:
                third, fourth = "先别记消耗，我只是问问", "现在帮我登记消耗两盒吧"
            rows.append({"id": f"p85-{group:02}-{variant}", "group_id": f"p85-family-{group:02}",
                "split": "dev" if group <= 6 else "holdout", "synthetic": True,
                "source": "Project-authored six-turn household scenario; no downloaded benchmark examples",
                "human_review_status": "pending", "stock": str(4+variant*2), "action": action,
                "switch_object": group in {3, 4}, "change_stock": group == 5, "group": group,
                "turns": ["查一下牛奶的数量和位置", SOCIAL[variant], followup, third, fourth,
                          "为什么还没执行，还需要我做什么"]})
    return rows


def main():
    directory = Path(__file__).parent
    rows = scenarios()
    (directory/"scenarios.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows), encoding="utf-8")
    (directory/"manifest.json").write_text(json.dumps({"scenario_count": 40, "measured_turns": 240,
        "dev_scenarios": 24, "holdout_scenarios": 16, "dev_turns": 144, "holdout_turns": 96,
        "group_isolation": "semantic family, not utterance variants", "human_review_status": "pending",
        "source": "Original synthetic project scenarios inspired by memory evaluation categories, no upstream dataset copied",
        "seeded_history": "Ten non-model background turns are inserted after turn 2 to move the first topic out of the recent-ten window",
        "workflow_vs_model": "Fixture run measures workflow correctness; only --real measures provider understanding",
        "p84_data": "Unchanged; optional --baseline uses released P8.4 on identical scenarios"}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__": main()
