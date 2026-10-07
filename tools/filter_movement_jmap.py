#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
TARGETS=("RoboquestMovementComponent","Character_Player","CharacterMovementComponent")
TERMS=("RunMoveSpeed","CrouchMoveSpeed","SprintMoveSpeed","GroundAcceleration","AerialAcceleration","LandAcceleration","BaseGravity","GravityIncreasePerSecond","AirControl","BunnyJumpSpeedPercentModifier","DashSpeed","PowerSlide","Jetpack","RocketJump","CalcVelocity","PhysWalking","PhysFalling","PerformMovement","MoveAutonomous","Prediction","SavedMove","MaxAcceleration")
def walk(v:Any,path:str="$"):
 if isinstance(v,dict):
  yield path,v
  for k,c in v.items(): yield from walk(c,f"{path}.{k}")
 elif isinstance(v,list):
  for i,c in enumerate(v): yield from walk(c,f"{path}[{i}]")
def scalar_text(d): return " ".join(str(v) for v in d.values() if isinstance(v,(str,int,float,bool)))
def strings(v):
 out=[]
 if isinstance(v,dict):
  for c in v.values(): out+=strings(c)
 elif isinstance(v,list):
  for c in v: out+=strings(c)
 elif isinstance(v,str): out.append(v)
 return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument("jmap",type=Path);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args();data=json.loads(a.jmap.read_text(encoding="utf-8-sig"));matches=[];seen=set()
 for path,rec in walk(data):
  t=scalar_text(rec).lower()
  if not any(x.lower() in t for x in TARGETS): continue
  s=json.dumps(rec,sort_keys=True,ensure_ascii=False)
  if s in seen: continue
  seen.add(s); relevant=sorted({x for x in strings(rec) if any(y.lower() in x.lower() for y in TARGETS+TERMS)})
  matches.append({"path":path,"movement_strings":relevant,"record":rec})
 out={"schema_version":1,"source_file":a.jmap.name,"match_count":len(matches),"matches":matches};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");print(json.dumps({"matches":len(matches),"output":str(a.output)},indent=2));return 0
if __name__=="__main__": raise SystemExit(main())
