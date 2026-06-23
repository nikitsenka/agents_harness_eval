#!/usr/bin/env bash
# N=3 clean memory measurement: built-in vs Hindsight provider.
# Phase A: reliability (pass^3) + agent token/cost aggregates (full HM set x3 per condition).
# Phase B: Hindsight INTERNAL LLM tokens per scenario (run solo so the per-scenario
#          bank reset isolates each scenario's internal spend in the stats endpoint).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
SPEC=scenarios/memory-hard.yaml
SCN=hm1,hm2,hm3,hm4,hm5
HS_STATS="http://localhost:8889/v1/default/banks/hermes-eval/llm-requests/stats"
OUT=results/measure; mkdir -p "$OUT"
A=$OUT/agent.csv; B=$OUT/internal.csv
echo "phase,run,cond,scn,verdict,agent_total,agent_cost" > "$A"
echo "scn,verdict,agent_total,agent_cost,hs_internal_in,hs_internal_out,hs_internal_total" > "$B"

verdict(){ python3 -c "import json;print(json.load(open('$1/results.json'))['scenarios'][0]['verdict'])" 2>/dev/null; }
mtot(){ python3 -c "import json;m=json.load(open('$1/results.json'))['scenarios'][0]['metrics'] or {};print(int(m.get('total',0) or 0))" 2>/dev/null; }
mcost(){ python3 -c "import json;m=json.load(open('$1/results.json'))['scenarios'][0]['metrics'] or {};print(round(m.get('cost_usd',0) or 0,5))" 2>/dev/null; }
fulltot(){ python3 -c "import json;j=json.load(open('$1/results.json'));print(sum(int((s['metrics'] or {}).get('total',0) or 0) for s in j['scenarios']))" 2>/dev/null; }
fullcost(){ python3 -c "import json;j=json.load(open('$1/results.json'));print(round(sum((s['metrics'] or {}).get('cost_usd',0) or 0 for s in j['scenarios']),5))" 2>/dev/null; }
fullverds(){ python3 -c "import json;j=json.load(open('$1/results.json'));print(' '.join(f\"{s['id']}={s['verdict']}\" for s in j['scenarios']))" 2>/dev/null; }
hsstats(){ curl -s "$HS_STATS" | python3 -c "import json,sys;d=json.load(sys.stdin);b=d.get('buckets',[]);t=b[0]['tokens'] if b else {'input':0,'output':0,'total':0};print(t['input'],t['output'],t['total'])" 2>/dev/null; }

echo "=== $(date) PHASE A: reliability + agent cost (full set x3) ==="
for r in 1 2 3; do
  for cond in builtin hindsight; do
    flag=""; [ "$cond" = hindsight ] && flag="--hindsight"
    d=/tmp/measA_${cond}_$r
    python3 runners/run-eval.py --harness hermes --scenarios "$SPEC" --only "$SCN" $flag --no-judge --out "$d" >/dev/null 2>&1
    echo "A run$r $cond: $(fullverds "$d")  total=$(fulltot "$d") cost=$(fullcost "$d")"
    python3 -c "
import json,csv
j=json.load(open('$d/results.json'))
w=csv.writer(open('$A','a'))
for s in j['scenarios']:
    m=s['metrics'] or {}
    w.writerow(['A','$r','$cond',s['id'],s['verdict'],int(m.get('total',0) or 0),round(m.get('cost_usd',0) or 0,5)])
"
  done
done

echo "=== $(date) PHASE B: Hindsight internal tokens (solo per scenario) ==="
for s in hm1 hm2 hm3 hm4 hm5; do
  d=/tmp/measB_$s
  python3 runners/run-eval.py --harness hermes --scenarios "$SPEC" --only "$s" --hindsight --no-judge --out "$d" >/dev/null 2>&1
  sleep 4
  read -r hin hout htot <<<"$(hsstats)"
  echo "B $s: verdict=$(verdict "$d") agent_total=$(mtot "$d") hs_internal_total=$htot (in=$hin out=$hout)"
  echo "$s,$(verdict "$d"),$(mtot "$d"),$(mcost "$d"),$hin,$hout,$htot" >> "$B"
done
echo "=== DONE $(date) ==="
