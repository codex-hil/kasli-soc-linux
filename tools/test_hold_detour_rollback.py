#!/usr/bin/env python3
"""Execute the real C++ detour routine against a minimal routing graph."""
import argparse
from pathlib import Path
import subprocess
import tempfile

STUB = r'''
#include <map>
#include <set>
#include <vector>
#include <queue>
#include <limits>
#include <algorithm>
#include <cassert>
#include <iostream>
using delay_t=int;
struct Id { int i; Id(int v=-1):i(v){} bool operator==(Id o)const{return i==o.i;}
 bool operator!=(Id o)const{return i!=o.i;} bool operator<(Id o)const{return i<o.i;} };
using WireId=Id; using PipId=Id;
template<class K,class V> using dict=std::map<K,V>;
template<class K> using pool=std::set<K>;
constexpr int DETOUR_BBOX_MARGIN=8;
constexpr int STRENGTH_STRONG=1, STRENGTH_LOCKED=2;
struct Binding { PipId pip; int strength; };
struct NetInfo { dict<WireId,Binding> wires; };
struct Delay { int n; int maxDelay()const{return n;} };
struct Context {
 struct Edge { WireId src,dst; int delay; };
 std::vector<Edge> edges; NetInfo *net;
 std::vector<PipId> getPipsUphill(WireId w) {std::vector<PipId> r;for(int i=0;i<int(edges.size());++i)if(edges[i].dst==w)r.push_back(i);return r;}
 std::vector<PipId> getPipsDownhill(WireId w) {std::vector<PipId> r;for(int i=0;i<int(edges.size());++i)if(edges[i].src==w)r.push_back(i);return r;}
 WireId getPipSrcWire(PipId p){return edges[p.i].src;}
 WireId getPipDstWire(PipId p){return edges[p.i].dst;}
 Delay getPipDelay(PipId p){return {edges[p.i].delay};}
 NetInfo *getBoundWireNet(WireId w){return net->wires.count(w)?net:nullptr;}
 bool checkPipAvailForNet(PipId,NetInfo*){return true;}
 void unbindWire(WireId w){net->wires.erase(w);}
 void unbindPip(PipId p){unbindWire(getPipDstWire(p));}
 void bindPip(PipId p,NetInfo*n,int strength){n->wires[getPipDstWire(p)]={p,strength};}
};
static void wire_xy(Context*,WireId w,int &x,int &y){x=w.i;y=0;}
'''
MAIN = r'''
int main(){
 for(bool extra_path:{false,true}) {
  NetInfo n; Context c; c.net=&n;
  c.edges={{0,1,1},{1,3,1}};
  if(extra_path){c.edges.push_back({0,2,2});c.edges.push_back({2,3,2});}
  n.wires[0]={PipId(),STRENGTH_STRONG};
  c.bindPip(0,&n,STRENGTH_STRONG);c.bindPip(1,&n,STRENGTH_STRONG);
  bool result=detour_arc(&c,&n,3,extra_path?2:1);
  if(!extra_path){assert(!result);assert(n.wires.size()==3);
   assert(n.wires.at(1).pip==PipId(0));assert(n.wires.at(3).pip==PipId(1));
   assert(n.wires.at(1).strength==STRENGTH_STRONG);
   assert(n.wires.at(3).strength==STRENGTH_STRONG);
  }else{assert(result);assert(!n.wires.count(1));assert(n.wires.at(3).pip==PipId(3));}
 }
 std::cout<<"PASS: insufficient detour restores original route; sufficient detour commits\n";
}
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    args=parser.parse_args()
    text=args.source.read_text()
    routine=text[text.index('static bool detour_arc('):text.index('// Try to place `buf`')]
    with tempfile.TemporaryDirectory(prefix='detour-test-') as directory:
        root=Path(directory); source=root/'test.cc'; binary=root/'test'
        source.write_text(STUB+routine+MAIN)
        subprocess.run(['c++','-std=c++17','-O0',str(source),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)

if __name__=='__main__': main()
