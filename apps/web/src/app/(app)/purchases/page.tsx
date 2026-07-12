'use client';

import { Badge, Button, Card, CardContent, Input, Label, Modal, Spinner } from '@pharmaos/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import {
  ApiRequestError,
  createPurchaseSupplier,
  listPurchaseSuppliers,
  updatePurchaseSupplier,
  type SupplierDetail,
} from '@/lib/api';
import { t } from '@/lib/i18n';
import { toast } from '@/lib/toast-store';

interface SupplierForm {
  name: string;
  contact_name: string;
  phone: string;
  email: string;
  address: string;
  tax_registration_no: string;
  payment_terms: string;
  notes: string;
}

const EMPTY_FORM: SupplierForm = {
  name: '',
  contact_name: '',
  phone: '',
  email: '',
  address: '',
  tax_registration_no: '',
  payment_terms: '',
  notes: '',
};

/** Empty text -> null so optional fields clear cleanly (PATCH semantics). */
const nn = (v: string): string | null => (v.trim() === '' ? null : v.trim());

function formToPayload(f: SupplierForm): Record<string, unknown> {
  return {
    name: f.name.trim(),
    contact_name: nn(f.contact_name),
    phone: nn(f.phone),
    email: nn(f.email),
    address: nn(f.address),
    tax_registration_no: nn(f.tax_registration_no),
    payment_terms: nn(f.payment_terms),
    notes: nn(f.notes),
  };
}

function detailToForm(s: SupplierDetail): SupplierForm {
  return {
    name: s.name,
    contact_name: s.contact_name ?? '',
    phone: s.phone ?? '',
    email: s.email ?? '',
    address: s.address ?? '',
    tax_registration_no: s.tax_registration_no ?? '',
    payment_terms: s.payment_terms ?? '',
    notes: s.notes ?? '',
  };
}

export default function PurchasesPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [activeOnly, setActiveOnly] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<SupplierForm>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [editTarget, setEditTarget] = useState<SupplierDetail | null>(null);
  const [editForm, setEditForm] = useState<SupplierForm>(EMPTY_FORM);
  const [editError, setEditError] = useState<string | null>(null);

  const suppliersQuery = useQuery({
    queryKey: ['suppliers', search, activeOnly],
    queryFn: () => listPurchaseSuppliers({ search: search || undefined, activeOnly }),
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: ['suppliers'] });

  const createMut = useMutation({
    mutationFn: () =>
      createPurchaseSupplier({
        name: form.name.trim(),
        contact_name: nn(form.contact_name),
        phone: nn(form.phone),
        email: nn(form.email),
        address: nn(form.address),
        tax_registration_no: nn(form.tax_registration_no),
        payment_terms: nn(form.payment_terms),
        notes: nn(form.notes),
      }),
    onSuccess: () => {
      setShowForm(false);
      setForm(EMPTY_FORM);
      setFormError(null);
      invalidate();
      toast.success(t('purchases.created_ok'));
    },
    onError: (e) => setFormError(e instanceof ApiRequestError ? e.code : 'E-SYS-001'),
  });

  const editMut = useMutation({
    mutationFn: (id: string) => updatePurchaseSupplier(id, formToPayload(editForm)),
    onSuccess: () => {
      setEditTarget(null);
      setEditError(null);
      invalidate();
      toast.success(t('purchases.updated_ok'));
    },
    onError: (e) => setEditError(e instanceof ApiRequestError ? e.code : 'E-SYS-001'),
  });

  const activeMut = useMutation({
    mutationFn: (v: { id: string; active: boolean }) =>
      updatePurchaseSupplier(v.id, { is_active: v.active }),
    onSuccess: invalidate,
    onError: (e) => toast.error(t(`errors.${e instanceof ApiRequestError ? e.code : 'E-SYS-001'}`)),
  });

  const openEdit = (s: SupplierDetail) => {
    setEditTarget(s);
    setEditForm(detailToForm(s));
    setEditError(null);
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-900">{t('purchases.title')}</h1>
        <Button onClick={() => setShowForm((v) => !v)}>
          {showForm ? t('purchases.cancel') : t('purchases.add')}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Input
          className="max-w-xs"
          placeholder={t('purchases.search')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={(e) => setActiveOnly(e.target.checked)}
          />
          {t('purchases.active_only')}
        </label>
      </div>

      {showForm && (
        <Card>
          <CardContent className="pt-6">
            <form
              className="grid grid-cols-1 gap-4 sm:grid-cols-2"
              onSubmit={(e) => {
                e.preventDefault();
                createMut.mutate();
              }}
            >
              <Field label={t('purchases.name')}>
                <Input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required
                />
              </Field>
              <Field label={t('purchases.contact_name')}>
                <Input
                  value={form.contact_name}
                  onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
                />
              </Field>
              <Field label={t('purchases.phone')}>
                <Input
                  className="numeric"
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                />
              </Field>
              <Field label={t('purchases.email')}>
                <Input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </Field>
              <Field label={t('purchases.tax_no')}>
                <Input
                  value={form.tax_registration_no}
                  onChange={(e) => setForm({ ...form, tax_registration_no: e.target.value })}
                />
              </Field>
              <Field label={t('purchases.payment_terms')}>
                <Input
                  value={form.payment_terms}
                  onChange={(e) => setForm({ ...form, payment_terms: e.target.value })}
                />
              </Field>
              <Field label={t('purchases.address')}>
                <Input
                  value={form.address}
                  onChange={(e) => setForm({ ...form, address: e.target.value })}
                />
              </Field>
              <Field label={t('purchases.notes')}>
                <Input
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                />
              </Field>

              <div className="flex items-end gap-3">
                <Button type="submit" disabled={createMut.isPending}>
                  {createMut.isPending ? t('purchases.creating') : t('purchases.create')}
                </Button>
                {formError && (
                  <span className="text-sm text-danger">{t(`errors.${formError}`)}</span>
                )}
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="pt-6">
          {suppliersQuery.isLoading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : (
            <SupplierTable
              rows={suppliersQuery.data ?? []}
              onEdit={openEdit}
              onToggle={(s) => activeMut.mutate({ id: s.id, active: !s.is_active })}
            />
          )}
        </CardContent>
      </Card>

      <Modal
        open={editTarget !== null}
        onClose={() => setEditTarget(null)}
        title={t('purchases.edit_title')}
        className="max-w-2xl"
      >
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (editTarget) editMut.mutate(editTarget.id);
          }}
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label={t('purchases.name')}>
              <Input
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                required
              />
            </Field>
            <Field label={t('purchases.contact_name')}>
              <Input
                value={editForm.contact_name}
                onChange={(e) => setEditForm({ ...editForm, contact_name: e.target.value })}
              />
            </Field>
            <Field label={t('purchases.phone')}>
              <Input
                className="numeric"
                value={editForm.phone}
                onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
              />
            </Field>
            <Field label={t('purchases.email')}>
              <Input
                type="email"
                value={editForm.email}
                onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
              />
            </Field>
            <Field label={t('purchases.tax_no')}>
              <Input
                value={editForm.tax_registration_no}
                onChange={(e) => setEditForm({ ...editForm, tax_registration_no: e.target.value })}
              />
            </Field>
            <Field label={t('purchases.payment_terms')}>
              <Input
                value={editForm.payment_terms}
                onChange={(e) => setEditForm({ ...editForm, payment_terms: e.target.value })}
              />
            </Field>
            <Field label={t('purchases.address')}>
              <Input
                value={editForm.address}
                onChange={(e) => setEditForm({ ...editForm, address: e.target.value })}
              />
            </Field>
            <Field label={t('purchases.notes')}>
              <Input
                value={editForm.notes}
                onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
              />
            </Field>
          </div>
          {editError && <p className="text-sm text-danger">{t(`errors.${editError}`)}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setEditTarget(null)}>
              {t('purchases.cancel')}
            </Button>
            <Button type="submit" disabled={editMut.isPending}>
              {editMut.isPending ? t('purchases.saving') : t('purchases.save')}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

function SupplierTable({
  rows,
  onEdit,
  onToggle,
}: {
  rows: SupplierDetail[];
  onEdit: (s: SupplierDetail) => void;
  onToggle: (s: SupplierDetail) => void;
}) {
  if (rows.length === 0) {
    return <p className="py-8 text-center text-sm text-slate-500">{t('purchases.empty')}</p>;
  }
  return (
    <table className="w-full text-start text-sm">
      <thead>
        <tr className="border-b border-border text-start text-xs text-slate-500">
          <th className="p-2 text-start">{t('purchases.name')}</th>
          <th className="p-2 text-start">{t('purchases.contact_name')}</th>
          <th className="p-2 text-start">{t('purchases.phone')}</th>
          <th className="p-2 text-start">{t('purchases.tax_no')}</th>
          <th className="p-2 text-start">{t('purchases.payment_terms')}</th>
          <th className="p-2 text-start">{t('purchases.status')}</th>
          <th className="p-2 text-start">{t('purchases.actions')}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((s) => (
          <tr key={s.id} className="border-b border-border/60">
            <td className="p-2 font-medium text-slate-800">{s.name}</td>
            <td className="p-2 text-slate-700">{s.contact_name ?? '—'}</td>
            <td className="numeric p-2 text-slate-700">{s.phone ?? '—'}</td>
            <td className="numeric p-2 text-slate-700">{s.tax_registration_no ?? '—'}</td>
            <td className="p-2 text-slate-700">{s.payment_terms ?? '—'}</td>
            <td className="p-2">
              <Badge tone={s.is_active ? 'success' : 'neutral'}>
                {s.is_active ? t('purchases.active') : t('purchases.inactive')}
              </Badge>
            </td>
            <td className="flex flex-wrap gap-2 p-2">
              <Button size="sm" variant="ghost" onClick={() => onEdit(s)}>
                {t('purchases.edit')}
              </Button>
              <Button
                size="sm"
                variant={s.is_active ? 'outline' : 'primary'}
                onClick={() => onToggle(s)}
              >
                {s.is_active ? t('purchases.deactivate') : t('purchases.activate')}
              </Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
