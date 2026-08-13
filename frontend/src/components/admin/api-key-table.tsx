import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ApiKeyFixture } from "@/data/fixtures";

interface ApiKeyTableProps {
  keys: ApiKeyFixture[];
  onRevoke: (keyId: string) => void;
  disabled?: boolean;
}

export function ApiKeyTable({ keys, onRevoke, disabled }: ApiKeyTableProps) {
  return (
    <div
      className="overflow-x-auto rounded-panel border border-border-subtle"
      data-testid="api-key-table"
    >
      <table className="w-full text-left text-xs">
        <thead className="bg-bg-overlay text-text-secondary">
          <tr>
            <th className="px-3 py-2 font-medium">Key ID</th>
            <th className="px-3 py-2 font-medium">Prefix</th>
            <th className="px-3 py-2 font-medium">Scopes</th>
            <th className="px-3 py-2 font-medium">Created</th>
            <th className="px-3 py-2 font-medium">Last used</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="px-3 py-2 font-medium" />
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {keys.map((key) => (
            <tr key={key.key_id} data-testid={`api-key-row-${key.key_id}`}>
              <td className="px-3 py-2 font-mono text-text-primary">{key.key_id}</td>
              <td className="px-3 py-2 font-mono text-text-secondary">{key.prefix}</td>
              <td className="px-3 py-2">
                <div className="flex flex-wrap gap-1">
                  {key.scopes.map((scope) => (
                    <span
                      key={scope}
                      className="rounded-chip border border-border-subtle bg-bg-base px-1.5 py-0.5 text-[10px] text-text-secondary"
                    >
                      {scope}
                    </span>
                  ))}
                </div>
              </td>
              <td className="px-3 py-2 font-mono text-text-secondary">
                {new Date(key.created_at).toISOString()}
              </td>
              <td className="px-3 py-2 font-mono text-text-secondary">
                {key.last_used_at ? new Date(key.last_used_at).toISOString() : "Never"}
              </td>
              <td className="px-3 py-2">
                {key.revoked ? (
                  <Badge tone="danger" label="Revoked" />
                ) : (
                  <Badge tone="ok" label="Active" />
                )}
              </td>
              <td className="px-3 py-2 text-right">
                {!key.revoked && (
                  <Button
                    variant="danger"
                    size="sm"
                    data-testid={`revoke-key-${key.key_id}`}
                    disabled={disabled}
                    onClick={() => onRevoke(key.key_id)}
                  >
                    Revoke
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {keys.length === 0 && (
        <div className="p-4 text-center text-sm text-text-secondary">No API keys found.</div>
      )}
    </div>
  );
}
