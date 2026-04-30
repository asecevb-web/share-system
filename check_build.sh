#!/bin/bash
RUN=$(curl -s "https://api.github.com/repos/asecevb-web/share-system/actions/runs?per_page=1")
STATUS=$(echo "$RUN" | python3 -c 'import json,sys;r=json.loads(sys.stdin.read())["workflow_runs"][0];print(r["status"])')
CONCLUSION=$(echo "$RUN" | python3 -c 'import json,sys;r=json.loads(sys.stdin.read())["workflow_runs"][0];print(r.get("conclusion","进行中"))')

echo "构建状态: $STATUS | 结论: $CONCLUSION"

if [ "$STATUS" = "completed" ]; then
    if [ "$CONCLUSION" = "success" ]; then
        echo "BUILD_SUCCESS"
    else
        echo "BUILD_FAILED"
    fi
else
    echo "BUILD_IN_PROGRESS"
fi
