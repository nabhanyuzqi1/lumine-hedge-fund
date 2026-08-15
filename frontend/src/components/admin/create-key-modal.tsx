import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
const SCOPES = [
  "market.read",
  "portfolio.read",
  "portfolio.write",
  "orders.write",
  "journal.read",
  "admin.keys",
];

interface CreateKeyModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (scopes: string[]) => void;
}

export function CreateKeyModal({ open, onOpenChange, onCreate }: CreateKeyModalProps) {
  const [selected, setSelected] = React.useState<string[]>(["market.read", "portfolio.read"]);

  const toggleScope = (scope: string) => {
    setSelected((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope]
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onCreate(selected);
    setSelected(["market.read", "portfolio.read"]);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Create API key</DialogTitle>
            <DialogDescription>
              Select scopes for the new key. The secret is shown only once after creation.
            </DialogDescription>
          </DialogHeader>

          <div className="my-4 space-y-2">
            {SCOPES.map((scope) => (
              <label
                key={scope}
                className="flex items-center gap-2 rounded-chip border border-border-subtle bg-bg-base p-2 text-xs text-text-primary"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(scope)}
                  onChange={() => toggleScope(scope)}
                  data-testid={`create-key-scope-${scope}`}
                />
                <span className="font-mono">{scope}</span>
              </label>
            ))}
          </div>

          <DialogFooter>
            <Button type="button" variant="secondary" size="sm" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" size="sm" data-testid="create-key-submit">
              Create key
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
