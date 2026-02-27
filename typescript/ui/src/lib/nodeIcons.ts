/**
 * nodeIcons — maps node type names to Lucide icon components.
 *
 * Add a new entry here whenever a new node type is registered on the server.
 */
import {
  Box,
  Plus,
  X,
  Terminal,
  GitBranch,
  Repeat,
  List,
  Layers,
  Grid3X3,
  ListOrdered,
  FileText,
  Brain,
  Zap,
  Bot,
  Radio,
  Database,
  Scissors,
  Image,
  Eye,
  Sparkles,
  ShieldCheck,
  ScrollText,
  MessageSquare,
  CircleDot,
  type LucideIcon,
} from 'lucide-react';

// ── Icon map ──────────────────────────────────────────────────────────────────

export const NODE_ICON_MAP: Record<string, LucideIcon> = {
  // Core computation
  ConstantNode:        Box,
  AddNode:             Plus,
  MultiplyNode:        X,
  PrintNode:           Terminal,
  StepPrinterNode:     ListOrdered,
  AccumulatorNode:     Layers,
  VectorNode:          Grid3X3,

  // Control flow
  BranchNode:          GitBranch,
  ForLoopNode:         Repeat,
  ForEachNode:         List,

  // Language / LLM
  PromptTemplateNode:  FileText,
  LLMNode:             Brain,
  LLMStreamNode:       Zap,
  ToolAgentNode:       Bot,
  ToolAgentStreamNode: Radio,
  EmbeddingNode:       Database,
  TextSplitterNode:    Scissors,

  // Control flow (extended)
  WhileLoopNode:       Repeat,

  // Vision / image
  ImageGenNode:        Image,
  ImageGenExecNode:    Image,
  GPT4VisionNode:      Eye,

  // Prompt engineering
  PromptRefinerNode:    Sparkles,
  PromptRefineExecNode: Sparkles,

  // Privacy
  AnonymizerNode:      ShieldCheck,
  SummarizerNode:      ScrollText,

  // Agent nodes (pydantic-ai powered)
  PydanticAgentNode:   Bot,
  LLMCallNode:         Brain,
  AgentPlannerNode:    Sparkles,

  // Human-in-the-loop
  HumanInputNode:      MessageSquare,
};

// ── Getter ────────────────────────────────────────────────────────────────────

/** Returns the Lucide icon component for a given node type, or CircleDot as fallback. */
export function getNodeIcon(nodeType: string): LucideIcon {
  return NODE_ICON_MAP[nodeType] ?? CircleDot;
}
