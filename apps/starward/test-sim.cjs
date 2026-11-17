"use strict";
// No dependencies. Run: node apps/starward/test-sim.cjs
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const html = fs.readFileSync(path.join(__dirname, "starward.html"), "utf8");
const engine = html.match(/<script id="simulation-engine">([\s\S]*?)<\/script>/);
if (!engine) throw Error("Simulation engine not found in starward.html");
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
for (const [index, script] of scripts.entries()) new vm.Script(script[1], {filename:"starward-script-"+index+".js"});
const classes = vm.runInNewContext(engine[1] + "\n({C:StarshipSim,D:StarshipDefs});", {});
const results = (function (C, D) {

 const results=[];
 function test(name,fn){try{fn();results.push({name,passed:true});}catch(error){results.push({name,passed:false,error:error.message});}}
 function assert(ok,message="Assertion failed"){if(!ok)throw Error(message);}
 function run(sim,n){for(let i=0;i<n;i++)sim.step(1);return sim;}
 function isolated(seed=315){const s=new C(seed);s.s.tasks=[];s.s.directorAt=1e9;s.s.nextIncident=1e9;s.s.autoNav=false;return s;}
 function place(sim,c,id){const p=sim.point(id);c.room=id;c.x=p.x;c.y=p.y;c.path=[];c.destination=null;}
 test("All 16 agents have department heads and a captain",()=>{const s=new C(1);assert(s.alive().length===16);assert(s.captain().id==="vale");for(const dept of Object.keys(D.colors))assert(s.leader(dept));for(const t of s.s.tasks)assert(t.captain==="vale"&&s.crew(t.issuedBy));});
 test("Every ship room is reachable through adjacent rooms and ladders",()=>{const s=new C(1);for(const a of D.rooms)for(const b of D.rooms){const route=s.route(a.id,b.id);assert(Array.isArray(route));let prev=a;for(const id of route){const next=D.rooms.find(r=>r.id===id);assert(prev.row===next.row&&Math.abs(prev.col-next.col)===1||prev.col===next.col&&[1,3].includes(prev.col)&&Math.abs(prev.row-next.row)===1);prev=next;}assert(prev.id===b.id);}});
 test("Repair work honours diagnosis and fabrication dependencies",()=>{const s=isolated();s.repairPlan("reactor");const tasks=s.s.tasks;assert(tasks.map(t=>t.kind).join(",")==="diagnose,fabricate,repair");assert(!s.ready(tasks[1])&&!s.ready(tasks[2]));run(s,250);assert(tasks.every(t=>t.status==="done"));assert(s.room("reactor").integrity===100);assert(s.s.scrap===44&&s.s.parts===10);});
 test("Resource reservation is spent once despite interruption",()=>{const s=isolated();const t=s.add("fabricate","workshop");assert(s.begin(t));const count=s.s.scrap;assert(s.begin(t));assert(s.s.scrap===count);});
 test("Injured patients remain in treatment until medically cleared",()=>{const s=isolated();s.crew("kit").health=40;s.add("treat","medbay",{target:"kit",priority:100});run(s,120);assert(s.crew("kit").health===100);assert(s.crew("kit").need!=="medical");assert(s.s.medkits===11);});
 test("Both critically injured doctors recover and resume treatment",()=>{const s=new C(1);s.s.autoNav=false;s.s.nextIncident=1e9;s.crew("sol").health=35;s.crew("reed").health=35;run(s,600);assert(s.crew("sol").health===100&&s.crew("reed").health===100);});
 test("General operations crew fills a missing medical department",()=>{const s=isolated();for(const c of s.s.crew.filter(c=>c.dept==="medical"))c.dead=true;s.crew("kit").health=40;s.add("treat","medbay",{target:"kit",priority:100});run(s,240);assert(s.crew("kit").health===100);assert(s.s.tasks[0].status==="done");C.restore(s.export());});
 test("Emergency fire response interrupts routine assignments",()=>{const s=new C(1);run(s,2);s.incident("fire");run(s,2);assert(s.s.tasks.some(t=>t.kind==="fire"&&t.assignee));run(s,200);assert(s.s.rooms.every(r=>r.fire===0));});
 test("Medical emergencies consume kits without negative inventory",()=>{const s=new C(1);s.s.medkits=0;s.crew("kit").health=45;run(s,300);assert(s.s.medkits>=0);assert(s.crew("kit").health===100);});
 test("Zero-material repairs recover through salvage and fabrication",()=>{const s=new C(1);s.s.scrap=0;s.s.parts=0;s.s.nextIncident=1e9;run(s,600);assert(s.room("reactor").integrity===100);assert(s.s.scrap>=0&&s.s.parts>=0);});
 test("Rest and meals restore crew needs",()=>{const s=isolated();s.crew("kit").energy=10;s.crew("nova").hunger=5;run(s,180);assert(s.crew("kit").energy>80&&s.crew("nova").hunger>80);assert(s.s.food<74);});
 test("Blueprints stay locked until research completes",()=>{const s=isolated();assert(!s.queueBuild("drone"));s.s.technologies.push("drone");assert(s.queueBuild("drone"));assert(!s.queueBuild("drone"));run(s,180);assert(s.s.built.includes("drone"));});
 test("Navigation rejects non-adjacent destinations and spends one fuel",()=>{const s=isolated();assert(!s.jump(7));const before=s.s.fuel;assert(s.jump(1));assert(!s.jump(2));run(s,180);assert(s.s.sector===1&&s.s.fuel===before-1);});
 test("Pause freezes the entire simulation state",()=>{const s=new C(1);s.s.paused=true;const before=s.export();run(s,100);assert(s.export()===before);});
 test("Captain loss triggers executive-officer succession",()=>{const s=new C(1);s.crew("vale").health=0;run(s,1);assert(s.captain().id==="holt");assert(s.setFocus("repair"));assert(s.s.orders[0].by==="holt");});
 test("Save roundtrip resumes with deterministic state and RNG",()=>{const s=run(new C(42),400),restored=C.restore(s.export());assert(restored.export()===s.export());run(s,300);run(restored,300);assert(restored.export()===s.export());});
 test("Imported saves reject negative resources, orphan claims and unknown records",()=>{for(const mutate of [s=>s.scrap=-1,s=>s.crew[0].task="T999",s=>s.rooms[0].id="unknown",s=>s.tasks[0].depends=[s.tasks[0].id],s=>s.crew[0].path=["hangar"]]){const s=new C(1),j=JSON.parse(s.export());mutate(j.state);let rejected=false;try{C.restore(JSON.stringify(j));}catch(e){rejected=true;}assert(rejected);}});
 test("Untrusted extra keys are removed from restored records",()=>{const s=new C(1),j=JSON.parse(s.export());j.state.rooms[0].injected="untrusted";j.state.crew[0].injected="untrusted";const restored=C.restore(JSON.stringify(j));assert(!Object.hasOwn(restored.s.rooms[0],"injected")&&!Object.hasOwn(restored.s.crew[0],"injected"));});
 test("Imported text cannot change canonical identities",()=>{const j=JSON.parse(new C(1).export());j.state.crew[0].name="<script>";let rejected=false;try{C.restore(JSON.stringify(j));}catch(e){rejected=true;}assert(rejected);});
 test("Hull loss ends the mission and freezes subsequent ticks",()=>{const s=new C(1);s.s.hull=0;s.step(1);assert(s.s.gameover&&s.s.paused);const before=s.export();s.step(1);assert(s.export()===before);});
 test("Three 40-minute voyages preserve invariants and complete the expedition",()=>{for(const seed of [1,315,999]){const s=run(new C(seed),2400);assert(s.alive().length===16&&s.s.victory);assert(s.s.scanned.length===8&&s.s.technologies.length===5&&s.s.built.length===3);assert(s.s.tasks.length<=220&&s.s.log.length<=120);for(const k of ["scrap","parts","food","medkits","data","fuel"])assert(s.s[k]>=0);for(const c of s.s.crew){assert(c.memory.length<=8);if(c.task)assert(s.s.tasks.find(t=>t.id===c.task)?.assignee===c.id);}C.restore(s.export());}});
 return results;

})(classes.C, classes.D);
for (const result of results) console.log((result.passed ? "PASS " : "FAIL ") + result.name + (result.error ? ": " + result.error : ""));
console.log(results.filter(result => result.passed).length + "/" + results.length + " simulation tests passed");
if (results.some(result => !result.passed)) process.exitCode = 1;
