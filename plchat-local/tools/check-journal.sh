#!/usr/bin/env bash
# check-journal.sh —— 看一眼 review 队列里现在有什么(计划步骤 / 脚本文件)
# 用法: bash check-journal.sh
set -u
WS="${NX_SKILL_WORKSPACE:-/e/AIprojects/nx-workspace}"
echo "=== review 目录 ($WS/review) ==="
find "$WS/review" -type f 2>/dev/null | sed "s|.*/review/||" || echo "  (空)"
echo
echo "=== plan.json 步骤 ==="
PLAN="$WS/review/plan.json"
if [ -f "$PLAN" ]; then
  node -e "
    const p=require(process.argv[1]);
    (p.steps||[]).forEach(function(s){
      console.log('  '+s.id, String(s.name).padEnd(26), String(s.operation).padEnd(14),
                  String(s.gate||'').padEnd(7), JSON.stringify(s.params||{}));
    });" "$PLAN"
else
  echo "  (没有 plan.json)"
fi
echo
echo "=== scripts 目录 ==="
ls -la "$WS/review/scripts/" 2>/dev/null | awk 'NR>3 {print $5, $9}' || echo "  (空)"
