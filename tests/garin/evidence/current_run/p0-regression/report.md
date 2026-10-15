# 回归测试报告
版本：5a056831799b-p0-regression-rules；引擎：rules；适配器：adapters.local_p0
结果：{'PASS': 242, 'FAIL': 18, 'REVIEW': 18}；本轮必测项全部通过：False

## 失败、阻塞与待定项
- p0-33-0 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'ADD', 'name': '饼干', 'quantity': '2', 'unit': '袋', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}; actual=None
- p0-33-1 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'ADD', 'name': '饼干', 'quantity': '2', 'unit': '袋', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}; actual=None
- p0-33-2 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'ADD', 'name': '饼干', 'quantity': '2', 'unit': '袋', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}; actual=None
- p0-43-2 [REVIEW]：gold label awaiting approval
- ext-002 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'ADD', 'name': '饼干', 'quantity': '3', 'unit': '包', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}; actual=None
- ext-004 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'ADD', 'name': '垃圾袋', 'quantity': '2', 'unit': '卷', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}; actual=None
- ext-013 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'PLAN_ADD', 'name': '饼干', 'quantity': '3', 'unit': '包', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}; actual=None
- ext-015 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'PLAN_ADD', 'name': '垃圾袋', 'quantity': '2', 'unit': '卷', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}; actual=None
- ext-023 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'ADD', 'name': '鸡蛋', 'quantity': '12', 'unit': '个', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}; actual=None
- ext-024 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'ADD', 'name': '鸡蛋', 'quantity': '21', 'unit': '个', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}; actual=None
- ext-026 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'ADD', 'name': '饼干', 'quantity': '3', 'unit': '包', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}; actual=None
- ext-027 [FAIL]：status: expected='needs_confirmation'; actual='unsupported'；draft: expected={'action': 'ADD', 'name': '和润牛奶', 'quantity': '2', 'unit': '盒', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}; actual=None
- ext-028 [FAIL]：status: expected='needs_confirmation'; actual='unsupported'；draft: expected={'action': 'ADD', 'name': '和味饼干', 'quantity': '2', 'unit': '包', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}; actual=None
- ext-039 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'ADD', 'name': '牛奶', 'quantity': '2', 'unit': '盒', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': '2026-10-08', 'label_expiry': None}; actual=None
- ext-040 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'ADD', 'name': '牛奶', 'quantity': '2', 'unit': '盒', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': '2024-02-29', 'label_expiry': None}; actual=None
- ext-041 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'ADD', 'name': '牛奶', 'quantity': '2', 'unit': '盒', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': '2026-01-01', 'label_expiry': None}; actual=None
- ext-042 [FAIL]：status: expected='needs_confirmation'; actual='needs_clarification'；draft: expected={'action': 'ADD', 'name': '牛奶', 'quantity': '2', 'unit': '盒', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': '2026-10-08', 'label_expiry': '2026-10-15'}; actual=None
- ext-049 [FAIL]：status: expected='needs_clarification'; actual='needs_confirmation'；draft: expected=None; actual={'action': 'ADD', 'name': '牛奶', 'quantity': '2.0', 'unit': '盒', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}
- ext-075 [REVIEW]：gold label awaiting approval
- ext-076 [REVIEW]：gold label awaiting approval
- ext-077 [REVIEW]：gold label awaiting approval
- ext-081 [FAIL]：status: expected='unsupported'; actual='needs_clarification'
- ext-083 [REVIEW]：gold label awaiting approval
- ext-084 [REVIEW]：gold label awaiting approval
- ext-085 [REVIEW]：gold label awaiting approval
- ext-086 [REVIEW]：gold label awaiting approval
- ext-087 [REVIEW]：gold label awaiting approval
- ext-088 [REVIEW]：gold label awaiting approval
- ext-089 [REVIEW]：gold label awaiting approval
- ext-090 [REVIEW]：gold label awaiting approval
- ext-091 [REVIEW]：gold label awaiting approval
- ext-092 [REVIEW]：gold label awaiting approval
- ext-093 [REVIEW]：gold label awaiting approval
- ext-094 [REVIEW]：gold label awaiting approval
- ext-095 [REVIEW]：gold label awaiting approval
- ext-096 [REVIEW]：gold label awaiting approval