"""
Authoritative TraceEvent type definitions — mirrors server/src/trace/traceTypes.ts exactly.
All events are plain dicts so they can be emitted over Socket.IO without Pydantic overhead.
"""
from typing import Any, Dict, Literal, TypedDict, Union


class ExecStartEvent(TypedDict):
    type: Literal["EXEC_START"]
    networkId: str
    rootNodeId: str
    ts: int


class NodeRunningDebugFields(TypedDict, total=False):
    networkId: str
    nodeName: str
    nodePath: str


class NodeRunningEvent(NodeRunningDebugFields):
    type: Literal["NODE_RUNNING"]
    nodeId: str
    ts: int


class NodeDoneDebugFields(TypedDict, total=False):
    networkId: str
    nodeName: str
    nodePath: str


class NodeDoneEvent(NodeDoneDebugFields):
    type: Literal["NODE_DONE"]
    nodeId: str
    durationMs: float
    ts: int


class NodeErrorDebugFields(TypedDict, total=False):
    networkId: str
    nodeName: str
    nodePath: str
    durationMs: float


class NodeErrorEvent(NodeErrorDebugFields):
    type: Literal["NODE_ERROR"]
    nodeId: str
    error: str
    ts: int


class EdgeActiveEvent(TypedDict):
    type: Literal["EDGE_ACTIVE"]
    fromNodeId: str
    fromPort: str
    toNodeId: str
    toPort: str
    ts: int


class StepPauseEvent(TypedDict):
    type: Literal["STEP_PAUSE"]
    nodeId: str
    ts: int


class ExecDoneEvent(TypedDict):
    type: Literal["EXEC_DONE"]
    networkId: str
    ts: int


class ExecErrorEvent(TypedDict):
    type: Literal["EXEC_ERROR"]
    networkId: str
    error: str
    ts: int


TraceEvent = Union[
    ExecStartEvent,
    NodeRunningEvent,
    NodeDoneEvent,
    NodeErrorEvent,
    EdgeActiveEvent,
    StepPauseEvent,
    ExecDoneEvent,
    ExecErrorEvent,
]
