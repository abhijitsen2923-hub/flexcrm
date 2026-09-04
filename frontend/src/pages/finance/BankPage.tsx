import { useEffect, useMemo, useState } from "react";

import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  KpiCard,
  LoadingBlock,
  Modal,
  SelectField,
  TextField,
  TextareaField,
  useToast,
  type DataTableColumn
} from "../../components";
import { usePermissions } from "../../hooks/usePermissions";
import { financeService } from "../../services/finance";
import type {
  BankTransaction,
  FinanceAccount,
  FinanceCategory
} from "../../types/finance";
import { extractErrorMessage } from "../../utils/errors";
import { formatCurrency, formatDate } from "../../utils/format";

const today = () => new Date().toISOString().slice(0, 10);

const ACCOUNT_FORM = {
  name: "",
  account_type: "bank" as "bank" | "cash",
  opening_balance: "",
  account_number: "",
  ifsc: "",
  notes: ""
};

const TXN_FORM = {
  txn_date: today(),
  description: "",
  direction: "out" as "in" | "out",
  amount: "",
  reference: "",
  category_id: ""
};

export default function BankPage() {
  const toast = useToast();
  const { has } = usePermissions();
  const canManageAccounts = has("FINANCE_SETTINGS_MANAGE");
  const canRecord = has("FINANCE_RECORD_PAYMENT");

  const [accounts, setAccounts] = useState<FinanceAccount[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [transactions, setTransactions] = useState<BankTransaction[]>([]);
  const [categories, setCategories] = useState<FinanceCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [txnLoading, setTxnLoading] = useState(false);

  const [acctModal, setAcctModal] = useState(false);
  const [acctForm, setAcctForm] = useState(ACCOUNT_FORM);
  const [savingAcct, setSavingAcct] = useState(false);

  const [txnModal, setTxnModal] = useState(false);
  const [txnForm, setTxnForm] = useState(TXN_FORM);
  const [savingTxn, setSavingTxn] = useState(false);

  const [statement, setStatement] = useState("");

  const selected = useMemo(() => accounts.find((a) => a.id === selectedId) ?? null, [accounts, selectedId]);
  const categoryOptions = useMemo(
    () => categories.filter((c) => c.is_active).map((c) => ({ value: c.id, label: c.name })),
    [categories]
  );

  async function loadAccounts(selectAfter?: string) {
    setLoading(true);
    try {
      const [list, cats] = await Promise.all([
        financeService.listAccounts(true),
        categories.length ? Promise.resolve(categories) : financeService.listCategories()
      ]);
      setAccounts(list);
      if (!categories.length) setCategories(cats);
      const next = selectAfter ?? selectedId ?? (list[0]?.id ?? null);
      setSelectedId(next && list.some((a) => a.id === next) ? next : list[0]?.id ?? null);
    } catch (e) {
      toast.error("Failed to load accounts", extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void loadAccounts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadTransactions(accountId: string) {
    setTxnLoading(true);
    try {
      setTransactions(await financeService.listTransactions(accountId));
    } catch (e) {
      toast.error("Failed to load transactions", extractErrorMessage(e));
    } finally {
      setTxnLoading(false);
    }
  }
  useEffect(() => {
    if (selectedId) void loadTransactions(selectedId);
    else setTransactions([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  async function refreshSelected() {
    // Reload both the account (balances) and its transactions.
    await loadAccounts(selectedId ?? undefined);
    if (selectedId) await loadTransactions(selectedId);
  }

  async function saveAccount() {
    if (!acctForm.name.trim()) {
      toast.error("Account name is required");
      return;
    }
    setSavingAcct(true);
    try {
      const created = await financeService.createAccount({
        name: acctForm.name.trim(),
        account_type: acctForm.account_type,
        opening_balance: Number(acctForm.opening_balance || 0),
        account_number: acctForm.account_number.trim() || null,
        ifsc: acctForm.ifsc.trim() || null,
        notes: acctForm.notes.trim() || null
      });
      toast.success("Account created");
      setAcctModal(false);
      setAcctForm(ACCOUNT_FORM);
      await loadAccounts(created.id);
    } catch (e) {
      toast.error("Save failed", extractErrorMessage(e));
    } finally {
      setSavingAcct(false);
    }
  }

  async function deleteAccount() {
    if (!selected) return;
    if (!window.confirm(`Delete account "${selected.name}"? Its transactions are removed too.`)) return;
    try {
      await financeService.deleteAccount(selected.id);
      toast.success("Account deleted");
      setSelectedId(null);
      await loadAccounts();
    } catch (e) {
      toast.error("Delete failed", extractErrorMessage(e));
    }
  }

  async function saveTxn() {
    if (!selected) return;
    const amt = Number(txnForm.amount);
    if (!txnForm.description.trim() || !(amt > 0)) {
      toast.error("Description and a positive amount are required");
      return;
    }
    setSavingTxn(true);
    try {
      await financeService.createTransaction(selected.id, {
        txn_date: txnForm.txn_date,
        description: txnForm.description.trim(),
        direction: txnForm.direction,
        amount: amt,
        reference: txnForm.reference.trim() || null,
        category_id: txnForm.category_id || null
      });
      toast.success("Transaction added");
      setTxnModal(false);
      setTxnForm({ ...TXN_FORM, txn_date: txnForm.txn_date });
      await refreshSelected();
    } catch (e) {
      toast.error("Save failed", extractErrorMessage(e));
    } finally {
      setSavingTxn(false);
    }
  }

  async function toggleReconciled(t: BankTransaction, value: boolean) {
    try {
      await financeService.updateTransaction(t.id, { is_reconciled: value });
      await refreshSelected();
    } catch (e) {
      toast.error("Update failed", extractErrorMessage(e));
    }
  }

  async function deleteTxn(t: BankTransaction) {
    if (!window.confirm("Delete this transaction?")) return;
    try {
      await financeService.deleteTransaction(t.id);
      toast.success("Transaction deleted");
      await refreshSelected();
    } catch (e) {
      toast.error("Delete failed", extractErrorMessage(e));
    }
  }

  const reconDiff = useMemo(() => {
    if (!selected || statement === "") return null;
    return Number(statement) - Number(selected.cleared_balance);
  }, [selected, statement]);

  const columns: DataTableColumn<BankTransaction>[] = [
    { key: "date", header: "Date", render: (t) => formatDate(t.txn_date) },
    {
      key: "desc",
      header: "Description",
      render: (t) => (
        <div>
          <strong>{t.description}</strong>
          <div className="muted text-xs">
            {t.category_name ?? "—"}
            {t.reference ? ` · ${t.reference}` : ""}
          </div>
        </div>
      )
    },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      render: (t) => (
        <strong style={{ color: t.direction === "in" ? "#16a34a" : "#dc2626" }}>
          {t.direction === "in" ? "+" : "−"}
          {formatCurrency(t.amount, "INR")}
        </strong>
      )
    },
    {
      key: "reconciled",
      header: "Cleared",
      align: "center",
      render: (t) =>
        canRecord ? (
          <input
            type="checkbox"
            checked={t.is_reconciled}
            onChange={(e) => void toggleReconciled(t, e.target.checked)}
            title={t.is_reconciled ? `Reconciled ${t.reconciled_on ?? ""}` : "Mark reconciled"}
          />
        ) : (
          <Badge tone={t.is_reconciled ? "success" : "neutral"}>{t.is_reconciled ? "Yes" : "No"}</Badge>
        )
    }
  ];

  if (canRecord) {
    columns.push({
      key: "actions",
      header: "",
      align: "right",
      render: (t) => (
        <Button size="sm" variant="ghost" onClick={() => void deleteTxn(t)}>Delete</Button>
      )
    });
  }

  if (loading && accounts.length === 0) return <LoadingBlock label="Loading accounts…" />;

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Bank &amp; Cash</h1>
          <p>Track balances across bank and cash accounts, and reconcile against statements.</p>
        </div>
        {canManageAccounts && <Button onClick={() => setAcctModal(true)}>New Account</Button>}
      </div>

      {accounts.length === 0 ? (
        <Card>
          <EmptyState
            title="No accounts yet"
            description={canManageAccounts ? "Add a bank or cash account to start tracking money movements." : "No accounts have been set up."}
          />
        </Card>
      ) : (
        <>
          {/* Account selector chips */}
          <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap", marginBottom: "1rem" }}>
            {accounts.map((a) => (
              <button
                key={a.id}
                className={["chip", a.id === selectedId ? "chip--active" : null].filter(Boolean).join(" ")}
                onClick={() => setSelectedId(a.id)}
                style={{
                  padding: "0.5rem 0.85rem",
                  borderRadius: 8,
                  border: a.id === selectedId ? "2px solid var(--primary, #2563eb)" : "1px solid var(--border, #d1d5db)",
                  background: a.id === selectedId ? "var(--surface-2, #eff6ff)" : "var(--surface, #fff)",
                  cursor: "pointer",
                  textAlign: "left"
                }}
              >
                <div style={{ fontWeight: 600 }}>
                  {a.name} {!a.is_active && <Badge tone="neutral">inactive</Badge>}
                </div>
                <div className="muted text-xs">
                  {a.account_type === "cash" ? "Cash" : "Bank"} · {formatCurrency(a.current_balance, "INR")}
                </div>
              </button>
            ))}
          </div>

          {selected && (
            <>
              <div className="kpi-grid">
                <KpiCard label="Current balance" value={formatCurrency(selected.current_balance, "INR")} />
                <KpiCard label="Cleared balance" value={formatCurrency(selected.cleared_balance, "INR")} />
                <KpiCard label="Unreconciled" value={String(selected.unreconciled_count)} />
              </div>

              <Card title="Reconciliation">
                <div className="row" style={{ gap: "0.75rem", alignItems: "flex-end", flexWrap: "wrap" }}>
                  <TextField
                    id="stmt"
                    label="Statement closing balance (₹)"
                    type="number"
                    step="0.01"
                    value={statement}
                    onChange={(e) => setStatement(e.target.value)}
                  />
                  {reconDiff !== null && (
                    <div style={{ paddingBottom: 6 }}>
                      {Math.abs(reconDiff) < 0.005 ? (
                        <Badge tone="success">Reconciled — matches cleared balance</Badge>
                      ) : (
                        <Badge tone="warning">
                          Difference: {formatCurrency(Math.abs(reconDiff), "INR")}{" "}
                          {reconDiff > 0 ? "(statement higher)" : "(cleared higher)"}
                        </Badge>
                      )}
                    </div>
                  )}
                </div>
                <p className="muted text-sm" style={{ marginTop: "0.5rem" }}>
                  Tick transactions as they clear on your statement, then enter the statement's closing balance —
                  a zero difference means the account is reconciled.
                </p>
              </Card>

              <div className="page-header" style={{ marginTop: "1rem" }}>
                <div className="page-header__titles">
                  <h2 style={{ margin: 0 }}>{selected.name} · transactions</h2>
                </div>
                <div className="row" style={{ gap: "0.4rem" }}>
                  {canRecord && <Button onClick={() => setTxnModal(true)}>Add Transaction</Button>}
                  {canManageAccounts && (
                    <Button variant="ghost" onClick={() => void deleteAccount()}>Delete Account</Button>
                  )}
                </div>
              </div>

              <Card>
                {txnLoading ? (
                  <LoadingBlock label="Loading transactions…" />
                ) : (
                  <DataTable
                    columns={columns}
                    rows={transactions}
                    rowKey={(t) => t.id}
                    empty={<EmptyState title="No transactions" description="Add a deposit or withdrawal to get started." />}
                  />
                )}
              </Card>
            </>
          )}
        </>
      )}

      {/* New account */}
      <Modal
        open={acctModal}
        onClose={() => setAcctModal(false)}
        title="New Account"
        footer={
          <>
            <Button variant="secondary" onClick={() => setAcctModal(false)}>Cancel</Button>
            <Button loading={savingAcct} onClick={() => void saveAccount()}>Create</Button>
          </>
        }
      >
        <div className="form">
          <TextField id="a-name" label="Account name" value={acctForm.name} onChange={(e) => setAcctForm({ ...acctForm, name: e.target.value })} required />
          <div className="form-grid">
            <SelectField
              id="a-type"
              label="Type"
              value={acctForm.account_type}
              onChange={(e) => setAcctForm({ ...acctForm, account_type: e.target.value as "bank" | "cash" })}
              options={[
                { value: "bank", label: "Bank" },
                { value: "cash", label: "Cash" }
              ]}
            />
            <TextField id="a-open" label="Opening balance (₹)" type="number" step="0.01" value={acctForm.opening_balance} onChange={(e) => setAcctForm({ ...acctForm, opening_balance: e.target.value })} />
          </div>
          {acctForm.account_type === "bank" && (
            <div className="form-grid">
              <TextField id="a-num" label="Account number" value={acctForm.account_number} onChange={(e) => setAcctForm({ ...acctForm, account_number: e.target.value })} />
              <TextField id="a-ifsc" label="IFSC" value={acctForm.ifsc} onChange={(e) => setAcctForm({ ...acctForm, ifsc: e.target.value })} />
            </div>
          )}
          <TextareaField id="a-notes" label="Notes" rows={2} value={acctForm.notes} onChange={(e) => setAcctForm({ ...acctForm, notes: e.target.value })} />
        </div>
      </Modal>

      {/* Add transaction */}
      <Modal
        open={txnModal}
        onClose={() => setTxnModal(false)}
        title="Add Transaction"
        footer={
          <>
            <Button variant="secondary" onClick={() => setTxnModal(false)}>Cancel</Button>
            <Button loading={savingTxn} onClick={() => void saveTxn()}>Add</Button>
          </>
        }
      >
        <div className="form">
          <div className="form-grid">
            <TextField id="t-date" label="Date" type="date" value={txnForm.txn_date} onChange={(e) => setTxnForm({ ...txnForm, txn_date: e.target.value })} required />
            <SelectField
              id="t-dir"
              label="Direction"
              value={txnForm.direction}
              onChange={(e) => setTxnForm({ ...txnForm, direction: e.target.value as "in" | "out" })}
              options={[
                { value: "out", label: "Money out (withdrawal / payment)" },
                { value: "in", label: "Money in (deposit / receipt)" }
              ]}
            />
          </div>
          <TextField id="t-desc" label="Description" value={txnForm.description} onChange={(e) => setTxnForm({ ...txnForm, description: e.target.value })} required />
          <div className="form-grid">
            <TextField id="t-amt" label="Amount (₹)" type="number" min="0" step="0.01" value={txnForm.amount} onChange={(e) => setTxnForm({ ...txnForm, amount: e.target.value })} required />
            <TextField id="t-ref" label="Reference (optional)" value={txnForm.reference} onChange={(e) => setTxnForm({ ...txnForm, reference: e.target.value })} />
          </div>
          <SelectField
            id="t-cat"
            label="Category (optional)"
            value={txnForm.category_id}
            onChange={(e) => setTxnForm({ ...txnForm, category_id: e.target.value })}
            options={categoryOptions}
            placeholder="No category"
          />
        </div>
      </Modal>
    </>
  );
}
