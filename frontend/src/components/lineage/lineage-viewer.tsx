import { useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { LineageNode } from '@/data/fixtures';

interface LineageViewerProps {
  root: LineageNode;
  search?: string;
  defaultExpandedDepth?: number;
}

interface FlatNode {
  node: LineageNode;
  path: string;
  depth: number;
}

const TYPE_TONE: Record<LineageNode['type'], 'info' | 'ok' | 'warn' | 'danger' | 'neutral'> = {
  decision: 'info',
  input: 'neutral',
  output: 'ok',
  override: 'danger',
};

const TYPE_LABEL: Record<LineageNode['type'], string> = {
  decision: 'decision',
  input: 'input',
  output: 'output',
  override: 'override',
};

function flatten(node: LineageNode, path: string, depth: number, out: FlatNode[]) {
  out.push({ node, path, depth });
  node.children?.forEach((child) => flatten(child, `${path}.${child.id}`, depth + 1, out));
}

function nodeMatches(node: LineageNode, path: string, term: string) {
  if (!term) return true;
  const t = term.toLowerCase();
  return (
    node.label.toLowerCase().includes(t) ||
    node.detail?.toLowerCase().includes(t) ||
    path.toLowerCase().includes(t)
  );
}

function collectVisiblePaths(
  flat: FlatNode[],
  term: string,
): { visible: Set<string>; expanded: Set<string> } {
  const visible = new Set<string>();
  const expanded = new Set<string>();
  const childrenMap = new Map<string, string[]>();

  flat.forEach(({ node, path }) => {
    if (node.children) {
      childrenMap.set(
        path,
        node.children.map((c) => `${path}.${c.id}`),
      );
    }
  });

  // Mark nodes that match the search term as visible, and expand all ancestors.
  flat.forEach(({ node, path }) => {
    if (nodeMatches(node, path, term)) {
      visible.add(path);
      let p = path;
      while (p.includes('.')) {
        p = p.slice(0, p.lastIndexOf('.'));
        expanded.add(p);
        visible.add(p);
      }
    }
  });

  // If a parent is visible (because a descendant matched) keep it visible even
  // if it does not match the term.
  flat.forEach(({ path }) => {
    if (expanded.has(path)) visible.add(path);
  });

  return { visible, expanded };
}

interface TreeNodeProps {
  node: LineageNode;
  path: string;
  depth: number;
  searchTerm: string;
  defaultExpandedDepth: number;
  forceExpanded?: boolean;
  visiblePaths: Set<string>;
}

function TreeNode({
  node,
  path,
  depth,
  searchTerm,
  defaultExpandedDepth,
  forceExpanded,
  visiblePaths,
}: TreeNodeProps) {
  const hasChildren = (node.children?.length ?? 0) > 0;
  const [expanded, setExpanded] = useState(depth < defaultExpandedDepth);
  const isExpanded = forceExpanded || expanded;

  if (searchTerm && !visiblePaths.has(path)) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(path);
    } catch {
      // Clipboard may be unavailable in tests / insecure contexts.
    }
  };

  return (
    <li className="ml-0">
      <div className="group flex items-start gap-2 py-1">
        <button
          type="button"
          aria-label={isExpanded ? 'Collapse' : 'Expand'}
          className={cn(
            'mt-1 h-3 w-3 shrink-0 rounded-sm text-text-tertiary hover:text-text-primary',
            !hasChildren && 'invisible',
          )}
          onClick={() => setExpanded((e) => !e)}
          data-testid={`toggle-${node.id}`}
        >
          {isExpanded ? '▼' : '▶'}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={TYPE_TONE[node.type]} label={TYPE_LABEL[node.type]} />
            <span className="text-xs font-medium text-text-primary">{node.label}</span>
            {node.overridden && <Badge tone="danger" label="override" />}
            <Button
              variant="ghost"
              size="sm"
              className="h-5 px-1.5 text-[10px] opacity-0 transition-opacity group-hover:opacity-100"
              onClick={handleCopy}
              data-testid={`copy-path-${node.id}`}
            >
              copy path
            </Button>
          </div>
          {node.detail && <p className="mt-0.5 text-[11px] text-text-secondary">{node.detail}</p>}
        </div>
      </div>
      {hasChildren && isExpanded && (
        <ul className="border-l border-border-subtle pl-4">
          {node.children!.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              path={`${path}.${child.id}`}
              depth={depth + 1}
              searchTerm={searchTerm}
              defaultExpandedDepth={defaultExpandedDepth}
              forceExpanded={forceExpanded}
              visiblePaths={visiblePaths}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

/**
 * Recursive JSONB-style lineage tree. Supports search filtering, expand/collapse,
 * copy-path, and override badges. Defaults to expanding the first two levels.
 */
export function LineageViewer({ root, search = '', defaultExpandedDepth = 2 }: LineageViewerProps) {
  const flat = useMemo(() => {
    const out: FlatNode[] = [];
    flatten(root, root.id, 0, out);
    return out;
  }, [root]);

  const { visible: visiblePaths } = useMemo(
    () => collectVisiblePaths(flat, search.trim()),
    [flat, search],
  );

  const forceExpanded = search.trim().length > 0;
  const mergedVisible = forceExpanded ? visiblePaths : new Set(flat.map((f) => f.path));

  return (
    <div className="space-y-2" data-testid="lineage-viewer">
      <ul className="space-y-1">
        <TreeNode
          node={root}
          path={root.id}
          depth={0}
          searchTerm={search.trim()}
          defaultExpandedDepth={defaultExpandedDepth}
          forceExpanded={forceExpanded}
          visiblePaths={mergedVisible}
        />
      </ul>
    </div>
  );
}
