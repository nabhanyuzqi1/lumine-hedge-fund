import * as React from 'react';

import { useApiKeys, useCreateApiKey, useRevokeApiKey } from '@/api/hooks';
import { ApiKeyTable } from '@/components/admin/api-key-table';
import { CreateKeyModal } from '@/components/admin/create-key-modal';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/toast';

/**
 * `/admin/keys` — API key management (W6). Lists keys, creates new keys with a
 * one-time secret, and revokes existing keys. Fixture-backed until admin
 * backend is live.
 */
export function AdminKeysPage() {
  const { data: keys = [], isLoading } = useApiKeys();
  const create = useCreateApiKey();
  const revoke = useRevokeApiKey();
  const { toast } = useToast();

  const [createOpen, setCreateOpen] = React.useState(false);
  const [secret, setSecret] = React.useState<{ key_id: string; secret: string } | null>(null);
  const [revokeTarget, setRevokeTarget] = React.useState<string | null>(null);

  const handleCreate = (scopes: string[]) => {
    create.mutate(scopes, {
      onSuccess: (created) => {
        setSecret({ key_id: created.key_id, secret: created.secret });
        setCreateOpen(false);
        toast({ variant: 'success', title: 'API key created', description: created.key_id });
      },
    });
  };

  const confirmRevoke = () => {
    if (!revokeTarget) return;
    revoke.mutate(revokeTarget, {
      onSuccess: () => {
        setRevokeTarget(null);
        toast({ variant: 'warn', title: 'API key revoked', description: revokeTarget });
      },
    });
  };

  const handleCopySecret = async () => {
    if (!secret) return;
    try {
      await navigator.clipboard.writeText(secret.secret);
      toast({ variant: 'success', title: 'Secret copied to clipboard' });
    } catch {
      toast({ variant: 'danger', title: 'Failed to copy secret' });
    }
  };

  return (
    <div className="mx-auto w-full max-w-[1400px] space-y-4 p-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">API Keys</h1>
          <p className="text-sm text-text-secondary">Manage secrets and access scopes.</p>
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={() => setCreateOpen(true)}
          data-testid="create-key-button"
        >
          Create key
        </Button>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Keys</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-text-secondary">Loading keys…</p>
          ) : (
            <ApiKeyTable keys={keys} onRevoke={setRevokeTarget} />
          )}
        </CardContent>
      </Card>

      <CreateKeyModal open={createOpen} onOpenChange={setCreateOpen} onCreate={handleCreate} />

      <Dialog open={secret !== null} onOpenChange={(open) => !open && setSecret(null)}>
        <DialogContent data-testid="secret-dialog">
          <DialogHeader>
            <DialogTitle>API key secret</DialogTitle>
            <DialogDescription>Copy this secret now. It will not be shown again.</DialogDescription>
          </DialogHeader>
          {secret && (
            <div className="my-2 space-y-2">
              <p className="text-xs text-text-secondary">
                Key ID: <span className="font-mono text-text-primary">{secret.key_id}</span>
              </p>
              <div className="flex items-center gap-2 rounded-chip border border-border-subtle bg-bg-base p-2">
                <code
                  className="flex-1 break-all font-mono text-xs text-text-primary"
                  data-testid="secret-value"
                >
                  {secret.secret}
                </code>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleCopySecret}
                  data-testid="copy-secret"
                >
                  Copy
                </Button>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button
              variant="primary"
              size="sm"
              onClick={() => setSecret(null)}
              data-testid="close-secret"
            >
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={revokeTarget !== null} onOpenChange={(open) => !open && setRevokeTarget(null)}>
        <DialogContent data-testid="revoke-confirm-dialog">
          <DialogHeader>
            <DialogTitle>Revoke API key?</DialogTitle>
            <DialogDescription>
              This will immediately invalidate key <span className="font-mono">{revokeTarget}</span>
              . This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" size="sm" onClick={() => setRevokeTarget(null)}>
              Cancel
            </Button>
            <Button variant="danger" size="sm" onClick={confirmRevoke} data-testid="confirm-revoke">
              Revoke
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
