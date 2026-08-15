#!/bin/bash
# Copy source EA + compile v3.10 via Wine
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
# 1. copy source ke container
docker cp /opt/lumine/scripts/deploy/mt5/LumineEA.mq5 lumine-mt5:"/root/.wine-mt5/drive_c/Program Files/HFM Metatrader 5/MQL5/Experts/LumineEA.mq5"
echo "COPY_DONE"
# 2. compile
docker exec lumine-mt5 bash -c "
cd \"/root/.wine-mt5/drive_c/Program Files/HFM Metatrader 5\"
rm -f \"MQL5/logs/compile.log\"
WINEDEBUG=-all wine metaeditor64.exe /compile:\"MQL5/Experts/LumineEA.mq5\" /log:\"MQL5/logs/compile.log\" >/dev/null 2>&1
sleep 10
ls -la \"MQL5/Experts/LumineEA.ex5\" | awk \"{print \\\$5}\"
cat \"MQL5/logs/compile.log\" 2>/dev/null | grep -iE \"error|warning|result\" | head -6
"'
