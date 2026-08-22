"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  Layers,
  Search,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  ChevronDown,
  Scale,
  Sparkles,
} from "lucide-react";
import { SourceHierarchyNode } from "../lib/api";
import { useApp } from "../context/AppContext";

// Pure utility helper functions defined outside the React Component
function roundPercent(num: number, den: number): number {
  return roundTo((num / den) * 100, 2);
}

function roundTo(num: number, dec: number): number {
  return Math.round(num * Math.pow(10, dec)) / Math.pow(10, dec);
}

interface SourcePerformanceProps {
  sources: SourceHierarchyNode[];
  onSelectSource?: (mainSource: string, source: string) => void;
  isLoading?: boolean;
}

export const SourcePerformanceComponent: React.FC<SourcePerformanceProps> = ({
  sources = [],
  onSelectSource,
  isLoading = false,
}) => {
  const { theme } = useApp();
  const isDark = theme === "dark";

  // Search & Navigation states
  const [searchTerm, setSearchTerm] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [selectedNode, setSelectedNode] = useState<{
    node: SourceHierarchyNode;
    path: string[];
    rawPath: string[];
  } | null>(null);
  const [viewMode, setViewMode] = useState<"py_vs_cy" | "absolute" | "pct_change">("py_vs_cy");

  const safeSources = Array.isArray(sources) ? sources : [];

  // Compute "All Sources" totals lazily
  const allSourcesTotals = useMemo(() => {
    const totalLeads = safeSources.reduce((a, b) => a + (b?.leads || 0), 0);
    const totalCucet = safeSources.reduce((a, b) => a + (b?.cucet || 0), 0);
    const totalAdmission = safeSources.reduce((a, b) => a + (b?.admission || 0), 0);
    const totalPyLeads = safeSources.reduce((a, b) => a + (b?.py_leads || 0), 0);
    const totalPyCucet = safeSources.reduce((a, b) => a + (b?.py_cucet || 0), 0);
    const totalPyAdmission = safeSources.reduce((a, b) => a + (b?.py_admission || 0), 0);
    return {
      name: "All Sources",
      raw_name: "All Sources",
      leads: totalLeads,
      cucet: totalCucet,
      admission: totalAdmission,
      py_leads: totalPyLeads,
      py_cucet: totalPyCucet,
      py_admission: totalPyAdmission,
      performance: "normal",
    } as SourceHierarchyNode;
  }, [sources]);

  // Determine currently active selected node or default to All Sources
  const activeNode = useMemo(() => {
    return (
      selectedNode || {
        node: allSourcesTotals,
        path: ["All Sources"],
        rawPath: ["All Sources"],
      }
    );
  }, [selectedNode, allSourcesTotals]);

  // Expand parent nodes when search term changes
  useEffect(() => {
    if (!searchTerm) return;
    const lowerQuery = searchTerm.toLowerCase();
    const newExpanded: Record<string, boolean> = {};

    const checkAndExpand = (nodes: SourceHierarchyNode[], parentPath: string = "") => {
      nodes.forEach((node) => {
        const currentPath = parentPath ? `${parentPath} > ${node.name}` : node.name;
        const matchesSelf = node.name.toLowerCase().includes(lowerQuery);
        const matchesChild =
          node.children &&
          node.children.some(
            (c) =>
              c.name.toLowerCase().includes(lowerQuery) ||
              (c.children && c.children.some((gc) => gc.name.toLowerCase().includes(lowerQuery)))
          );

        if (matchesSelf || matchesChild) {
          newExpanded[currentPath] = true;
        }
        if (node.children) {
          checkAndExpand(node.children, currentPath);
        }
      });
    };

    checkAndExpand(sources);
    const timer = setTimeout(() => {
      setExpanded((prev) => ({ ...prev, ...newExpanded }));
    }, 0);
    return () => clearTimeout(timer);
  }, [searchTerm, sources]);

  // Recursively filter tree based on search query
  const filteredTree = useMemo(() => {
    if (!searchTerm) return sources;
    const lowerQuery = searchTerm.toLowerCase();

    const filterNodes = (nodes: SourceHierarchyNode[]): SourceHierarchyNode[] => {
      return nodes
        .map((node) => {
          const matchesSelf = node.name.toLowerCase().includes(lowerQuery);
          const filteredChildren = node.children ? filterNodes(node.children) : [];
          const matchesChild = filteredChildren.length > 0;

          if (matchesSelf || matchesChild) {
            return {
              ...node,
              children: node.children ? filteredChildren : undefined,
            } as SourceHierarchyNode;
          }
          return null;
        })
        .filter((n): n is SourceHierarchyNode => n !== null);
    };

    return filterNodes(sources);
  }, [sources, searchTerm]);

  // Toggle node expansion
  const toggleExpand = (pathKey: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpanded((prev) => ({
      ...prev,
      [pathKey]: !prev[pathKey],
    }));
  };

  // Select node in hierarchy
  const handleSelectNode = (node: SourceHierarchyNode, path: string[], rawPath: string[]) => {
    setSelectedNode({ node, path, rawPath });
  };

  // Return parent main source and current campaign name for L3
  const handleActionClick = (node: SourceHierarchyNode) => {
    if (activeNode.path.length === 2) {
      onSelectSource?.(node.raw_name, activeNode.rawPath[1]);
    }
  };

  // Recursive Tree Renderer
  const renderTree = (
    nodes: SourceHierarchyNode[],
    parentPath: string = "",
    parentRawPath: string[] = [],
    level: number = 0
  ) => {
    return (
      <ul className="space-y-1">
        {nodes.map((node) => {
          const currentPath = parentPath ? `${parentPath} > ${node.name}` : node.name;
          const currentRawPath = [...parentRawPath, node.raw_name];
          const isNodeExpanded = !!expanded[currentPath];
          const hasChildren = !!node.children && node.children.length > 0;
          const isSelected = activeNode.path.join(" > ") === currentPath;

          return (
            <li key={currentPath} className="space-y-1">
              <div
                onClick={() => {
                  const pathArray = parentPath ? [...parentPath.split(" > "), node.name] : [node.name];
                  handleSelectNode(node, pathArray, currentRawPath);
                }}
                style={{ paddingLeft: `${level * 12}px` }}
                className={`flex items-center justify-between py-1.5 pr-2 rounded-lg cursor-pointer transition-all ${
                  isSelected
                    ? "bg-blue-600/10 text-blue-400 font-bold border border-blue-500/20 shadow-xs"
                    : isDark
                    ? "text-slate-400 hover:text-slate-200 hover:bg-slate-900/50 border border-transparent"
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-50 border border-transparent"
                }`}
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  {hasChildren ? (
                    <button
                      onClick={(e) => toggleExpand(currentPath, e)}
                      className="p-1 rounded-md hover:bg-slate-800/40 text-slate-400 hover:text-slate-200 shrink-0"
                    >
                      {isNodeExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                    </button>
                  ) : (
                    <span className="w-6 shrink-0" />
                  )}
                  <span className="text-xs truncate">{node.name}</span>
                </div>
                <span className="text-[10px] font-mono text-slate-500 shrink-0">
                  {node.leads.toLocaleString()}
                </span>
              </div>

              {hasChildren && isNodeExpanded && (
                <div className="border-l border-slate-800/40 ml-4 pl-1">
                  {renderTree(node.children!, currentPath, currentRawPath, level + 1)}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    );
  };

  // Helper to determine conversion status
  const renderBadge = (flag: string) => {
    if (flag === "high_leads_low_conversion") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
          <AlertTriangle className="w-3 h-3 text-amber-500 shrink-0" />
          <span>High Leads / Low Conv</span>
        </span>
      );
    }
    if (flag === "strong") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
          <span>Strong</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold bg-slate-500/10 text-slate-400 border border-slate-500/20">
        <span>Normal</span>
      </span>
    );
  };

  const tableRows = useMemo<SourceHierarchyNode[]>(() => {
    const { node } = activeNode;

    if (node.name === "All Sources") {
      return sources;
    }
    if (node.children) {
      return node.children;
    }
    return [node];
  }, [activeNode, sources]);

  // Calculate Conversions and YoY metrics for selected node
  const metrics = useMemo(() => {
    const { node } = activeNode;
    
    const cyLeads = node.leads || 0;
    const pyLeads = node.py_leads || 0;
    const leadsChange = cyLeads - pyLeads;
    const leadsGrowth = pyLeads > 0 ? roundTo((leadsChange / pyLeads) * 100, 2) : 0;
    
    const cyAdmission = node.admission || 0;
    const pyAdmission = node.py_admission || 0;
    const admissionChange = cyAdmission - pyAdmission;
    const admissionGrowth = pyAdmission > 0 ? roundTo((admissionChange / pyAdmission) * 100, 2) : 0;
    
    const cyConversion = cyLeads > 0 ? roundTo((cyAdmission / cyLeads) * 100, 2) : 0.0;
    const pyConversion = pyLeads > 0 ? roundTo((pyAdmission / pyLeads) * 100, 2) : 0.0;
    const conversionChange = roundTo(cyConversion - pyConversion, 2);
    
    const cyCucet = cyLeads > 0 ? roundTo((node.cucet / cyLeads) * 100, 2) : 0.0;
    const pyCucet = pyLeads > 0 ? roundTo((node.py_cucet / pyLeads) * 100, 2) : 0.0;

    return {
      cyLeads,
      pyLeads,
      leadsChange,
      leadsGrowth,
      cyAdmission,
      pyAdmission,
      admissionChange,
      admissionGrowth,
      cyConversion,
      pyConversion,
      conversionChange,
      cyCucet,
      pyCucet,
    };
  }, [activeNode]);

  return (
    <div className={`grid grid-cols-1 lg:grid-cols-12 gap-6 ${isDark ? "text-slate-100" : "text-slate-900"}`}>
      {/* LEFT COLUMN: SOURCE HIERARCHY TREE */}
      <div className={`lg:col-span-4 p-5 rounded-2xl border flex flex-col h-[650px] overflow-hidden ${
        isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
      }`}>
        <div className="space-y-4 flex flex-col h-full">
          <div>
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-blue-400 animate-pulse shrink-0" />
              <span className="text-[10px] font-extrabold uppercase tracking-wider text-blue-400">
                Source Hierarchy
              </span>
            </div>
            <h2 className="text-sm font-extrabold tracking-tight mt-1">
              3-Level Category Explorer
            </h2>
          </div>

          {/* Search bar */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search campaigns, clusters..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className={`w-full pl-9 pr-3 py-2 text-xs font-semibold rounded-xl border focus:outline-none focus:ring-2 focus:ring-blue-500/20 ${
                isDark ? "bg-[#0B0F19] border-[#1E293B] text-white" : "bg-slate-50 border-slate-200 text-slate-700"
              }`}
            />
          </div>

          {/* Hierarchy Root elements */}
          <div className="flex-1 overflow-y-auto pr-1">
            {isLoading ? (
              <div className="flex flex-col items-center justify-center h-48 space-y-2">
                <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                <p className="text-[10px] text-slate-500">Loading taxonomy...</p>
              </div>
            ) : (
              <div className="space-y-2">
                {/* All Sources node */}
                <div
                  onClick={() => setSelectedNode(null)}
                  className={`flex items-center justify-between py-2 px-3 rounded-xl cursor-pointer transition-all border font-bold text-xs ${
                    activeNode.path[0] === "All Sources"
                      ? "bg-blue-600/10 text-blue-400 border-blue-500/20 shadow-xs"
                      : isDark
                      ? "text-slate-300 border-transparent hover:bg-slate-900/50"
                      : "text-slate-700 border-transparent hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-blue-400" />
                    <span>All Sources</span>
                  </div>
                  <span className="text-[10px] font-mono text-slate-500">
                    {safeSources.reduce((a, b) => a + (b?.leads || 0), 0).toLocaleString()}
                  </span>
                </div>

                <div className="border-t border-slate-800/40 my-2" />

                {/* Recursive tree nodes */}
                {renderTree(filteredTree, "", [])}

                {filteredTree.length === 0 && (
                  <p className="text-[10px] text-center text-slate-500 py-6">No matching nodes found.</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* RIGHT COLUMN: ANALYTICS DETAIL PANEL */}
      <div className="lg:col-span-8 space-y-6">
        {activeNode && (
          <>
            {/* Breadcrumb Header */}
            <div className={`p-4 rounded-xl border flex items-center justify-between text-xs font-semibold ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
            }`}>
              <div className="flex flex-wrap items-center gap-1 text-[11px] text-slate-400 font-bold uppercase tracking-wider">
                <span>Source Explorer</span>
                {activeNode.path.map((p, idx) => (
                  <React.Fragment key={idx}>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
                    <span className={idx === activeNode.path.length - 1 ? "text-blue-400" : ""}>{p}</span>
                  </React.Fragment>
                ))}
              </div>
              
              <div className="flex items-center gap-3">
                {/* Switcher */}
                <div className={`flex items-center gap-1 p-0.5 rounded-lg border ${
                  isDark ? "bg-slate-950/40 border-slate-800" : "bg-slate-100 border-slate-200"
                }`}>
                  <button
                    onClick={() => setViewMode("py_vs_cy")}
                    className={`px-2.5 py-1 text-[10px] font-extrabold rounded-md transition-all ${
                      viewMode === "py_vs_cy" 
                        ? (isDark ? "bg-blue-600 text-white shadow-md shadow-blue-500/20" : "bg-white text-blue-600 shadow-sm") 
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    PY vs CY
                  </button>
                  <button
                    onClick={() => setViewMode("absolute")}
                    className={`px-2.5 py-1 text-[10px] font-extrabold rounded-md transition-all ${
                      viewMode === "absolute" 
                        ? (isDark ? "bg-blue-600 text-white shadow-md shadow-blue-500/20" : "bg-white text-blue-600 shadow-sm") 
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Absolute
                  </button>
                  <button
                    onClick={() => setViewMode("pct_change")}
                    className={`px-2.5 py-1 text-[10px] font-extrabold rounded-md transition-all ${
                      viewMode === "pct_change" 
                        ? (isDark ? "bg-blue-600 text-white shadow-md shadow-blue-500/20" : "bg-white text-blue-600 shadow-sm") 
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    % Change
                  </button>
                </div>
                
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[9px] font-extrabold uppercase bg-blue-600/10 text-blue-400 border border-blue-500/20 rounded">
                  Level {activeNode.path[0] === "All Sources" ? 0 : activeNode.path.length}
                </span>
              </div>
            </div>

            {/* Selected Node Summary cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className={`p-4 rounded-2xl border ${
                isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-xs"
              }`}>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Leads</p>
                <div className="mt-2 space-y-1">
                  <div className="flex justify-between text-xs font-semibold">
                    <span className="text-slate-400">CY:</span>
                    <span className={isDark ? "text-white" : "text-slate-900"}>{metrics.cyLeads.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-xs font-semibold">
                    <span className="text-slate-400">PY:</span>
                    <span className={isDark ? "text-slate-300" : "text-slate-700"}>{metrics.pyLeads.toLocaleString()}</span>
                  </div>
                  {(viewMode === "py_vs_cy" || viewMode === "absolute") && (
                    <div className="flex justify-between text-xs font-semibold pt-1 border-t border-slate-800/20">
                      <span className="text-slate-400">Change:</span>
                      <span className={`font-bold ${metrics.leadsChange >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                        {metrics.leadsChange >= 0 ? "+" : ""}{metrics.leadsChange.toLocaleString()}
                      </span>
                    </div>
                  )}
                  {(viewMode === "py_vs_cy" || viewMode === "pct_change") && (
                    <div className="flex justify-between text-xs font-semibold pt-1 border-t border-slate-800/20">
                      <span className="text-slate-400">Growth:</span>
                      <span className={`font-bold ${metrics.leadsChange >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                        {metrics.leadsChange >= 0 ? "+" : ""}{metrics.leadsGrowth.toFixed(2)}%
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <div className={`p-4 rounded-2xl border ${
                isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-xs"
              }`}>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Admissions</p>
                <div className="mt-2 space-y-1">
                  <div className="flex justify-between text-xs font-semibold">
                    <span className="text-slate-400">CY:</span>
                    <span className={isDark ? "text-white" : "text-slate-900"}>{metrics.cyAdmission.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-xs font-semibold">
                    <span className="text-slate-400">PY:</span>
                    <span className={isDark ? "text-slate-300" : "text-slate-700"}>{metrics.pyAdmission.toLocaleString()}</span>
                  </div>
                  {(viewMode === "py_vs_cy" || viewMode === "absolute") && (
                    <div className="flex justify-between text-xs font-semibold pt-1 border-t border-slate-800/20">
                      <span className="text-slate-400">Change:</span>
                      <span className={`font-bold ${metrics.admissionChange >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                        {metrics.admissionChange >= 0 ? "+" : ""}{metrics.admissionChange.toLocaleString()}
                      </span>
                    </div>
                  )}
                  {(viewMode === "py_vs_cy" || viewMode === "pct_change") && (
                    <div className="flex justify-between text-xs font-semibold pt-1 border-t border-slate-800/20">
                      <span className="text-slate-400">Growth:</span>
                      <span className={`font-bold ${metrics.admissionChange >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                        {metrics.admissionChange >= 0 ? "+" : ""}{metrics.admissionGrowth.toFixed(2)}%
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <div className={`p-4 rounded-2xl border ${
                isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-xs"
              }`}>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Conversion</p>
                <div className="mt-2 space-y-1">
                  <div className="flex justify-between text-xs font-semibold">
                    <span className="text-slate-400">CY:</span>
                    <span className="text-blue-400 font-bold">{metrics.cyConversion.toFixed(2)}%</span>
                  </div>
                  <div className="flex justify-between text-xs font-semibold">
                    <span className="text-slate-400">PY:</span>
                    <span className="text-slate-400 font-bold">{metrics.pyConversion.toFixed(2)}%</span>
                  </div>
                  <div className="flex justify-between text-xs font-semibold pt-1 border-t border-slate-800/20">
                    <span className="text-slate-400">Change:</span>
                    <span className={`font-bold ${metrics.conversionChange >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {metrics.conversionChange >= 0 ? "+" : ""}{metrics.conversionChange.toFixed(2)} pp
                    </span>
                  </div>
                  <div className="flex justify-between text-xs font-semibold">
                    <span className="text-slate-400">Status:</span>
                    <span className="text-slate-400 font-bold text-[10px]">{activeNode.node.performance.replace(/_/g, " ").toUpperCase()}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Performance Summary block */}
            <div className={`p-4 rounded-2xl border ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
            }`}>
              <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider mb-2">Performance Summary</h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs font-bold">
                <div className="flex items-center justify-between sm:justify-start sm:gap-2">
                  <span className="text-slate-400">Leads:</span>
                  <span className={`flex items-center gap-1 font-extrabold ${metrics.leadsChange >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {metrics.leadsChange >= 0 ? "↑" : "↓"} {metrics.leadsChange >= 0 ? "+" : ""}{metrics.leadsChange.toLocaleString()} ({metrics.leadsGrowth >= 0 ? "+" : ""}{metrics.leadsGrowth.toFixed(2)}%)
                  </span>
                </div>
                <div className="flex items-center justify-between sm:justify-start sm:gap-2">
                  <span className="text-slate-400">Admissions:</span>
                  <span className={`flex items-center gap-1 font-extrabold ${metrics.admissionChange >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {metrics.admissionChange >= 0 ? "↑" : "↓"} {metrics.admissionChange >= 0 ? "+" : ""}{metrics.admissionChange.toLocaleString()} ({metrics.admissionGrowth >= 0 ? "+" : ""}{metrics.admissionGrowth.toFixed(2)}%)
                  </span>
                </div>
                <div className="flex items-center justify-between sm:justify-start sm:gap-2">
                  <span className="text-slate-400">Conversion:</span>
                  <span className={`flex items-center gap-1 font-extrabold ${metrics.conversionChange >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {metrics.conversionChange >= 0 ? "↑" : "↓"} {metrics.conversionChange >= 0 ? "+" : ""}{metrics.conversionChange.toFixed(2)} pp
                  </span>
                </div>
              </div>
            </div>

            {/* Selected Node Breakdown Table */}
            <div className={`p-5 rounded-2xl border ${
              isDark ? "bg-[#131B2E] border-[#1E293B]" : "bg-white border-slate-200 shadow-sm"
            }`}>
              <div className={`flex justify-between items-center pb-3 border-b mb-4 ${
                isDark ? "border-[#1E293B]" : "border-slate-200"
              }`}>
                <h3 className={`text-xs font-bold uppercase tracking-wider flex items-center gap-1.5 ${
                  isDark ? "text-white" : "text-slate-900"
                }`}>
                  <Scale className="w-4.5 h-4.5 text-blue-500" />
                  <span>Sub-channels Breakdown</span>
                </h3>
                <span className={`text-[10px] font-semibold ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                  Showing {tableRows.length} items
                </span>
              </div>

              <div className="overflow-x-auto w-full max-w-full">
                <table className={`w-full text-left text-xs ${isDark ? "text-slate-300" : "text-slate-700"}`}>
                  <thead>
                    <tr className={`border-b font-bold uppercase text-[9px] tracking-wider ${
                      isDark ? "border-[#1E293B]/50 text-slate-400" : "border-slate-200 text-slate-500 bg-slate-50"
                    }`}>
                      <th className="py-2.5 px-2">Name</th>
                      <th className="py-2.5 px-2 text-right">PY Leads</th>
                      <th className="py-2.5 px-2 text-right">CY Leads</th>
                      <th className="py-2.5 px-2 text-right">Lead Change</th>
                      <th className="py-2.5 px-2 text-right">PY Adm</th>
                      <th className="py-2.5 px-2 text-right">CY Adm</th>
                      <th className="py-2.5 px-2 text-right">Adm Change</th>
                      <th className="py-2.5 px-2 text-right">Conversion</th>
                      <th className="py-2.5 px-2 text-center">Status</th>
                      <th className="py-2.5 px-2 text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody className={`divide-y font-medium ${isDark ? "divide-[#1E293B]/40" : "divide-slate-100"}`}>
                    {tableRows.map((row: SourceHierarchyNode, idx) => {
                      const rowPath = [...activeNode.path, row.name];
                      const rowRawPath = [...activeNode.rawPath, row.raw_name];
                      const cyL = row.leads || 0;
                      const pyL = row.py_leads || 0;
                      const lChg = cyL - pyL;

                      const cyA = row.admission || 0;
                      const pyA = row.py_admission || 0;
                      const aChg = cyA - pyA;

                      const conv = cyL ? roundPercent(cyA, cyL) : 0;
                      return (
                        <tr
                          key={idx}
                          onClick={() => {
                            handleSelectNode(row, rowPath, rowRawPath);
                          }}
                          className={`cursor-pointer transition-colors duration-150 group text-[11px] ${
                            isDark ? "hover:bg-[#0B0F19]/45" : "hover:bg-slate-50"
                          }`}
                        >
                          <td className={`py-3 px-2 font-bold max-w-[110px] truncate ${isDark ? "text-slate-200" : "text-slate-900"}`}>
                            {row.name}
                          </td>
                          <td className={`py-3 px-2 text-right font-mono ${isDark ? "text-slate-400" : "text-slate-500"}`}>{pyL.toLocaleString()}</td>
                          <td className={`py-3 px-2 text-right font-mono font-bold ${isDark ? "text-white" : "text-slate-900"}`}>{cyL.toLocaleString()}</td>
                          <td className={`py-3 px-2 text-right font-mono font-semibold ${lChg >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                            {lChg >= 0 ? "+" : ""}{lChg.toLocaleString()}
                          </td>
                          <td className={`py-3 px-2 text-right font-mono ${isDark ? "text-slate-400" : "text-slate-500"}`}>{pyA.toLocaleString()}</td>
                          <td className={`py-3 px-2 text-right font-mono font-bold ${isDark ? "text-white" : "text-slate-900"}`}>{cyA.toLocaleString()}</td>
                          <td className={`py-3 px-2 text-right font-mono font-semibold ${aChg >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                            {aChg >= 0 ? "+" : ""}{aChg.toLocaleString()}
                          </td>
                          <td className="py-3 px-2 text-right font-mono text-blue-500 font-bold">{conv}%</td>
                          <td className="py-3 px-2 text-center">{renderBadge(row.performance)}</td>
                          <td className="py-3 px-2 text-center">
                            <button
                              onClick={(e) => {
                                  e.stopPropagation();
                                  handleActionClick(row);
                              }}
                              className="p-1 rounded-lg text-slate-400 group-hover:text-blue-500 shadow-2xs transition-all hover:scale-105"
                            >
                              <ChevronRight className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
