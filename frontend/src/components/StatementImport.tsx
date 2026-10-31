import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Loader,
  Modal,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { IconAlertTriangle, IconCircleCheck, IconFileUpload } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useMemo, useRef, useState, type DragEvent } from 'react';

import { api } from '../api';
import { money, monthLabel } from '../format';
import type { PreviewAccount, PreviewRow, StatementPreview } from '../types';
import CategorySelect from './CategorySelect';
import { FilterControl, useAppMutation } from './common';

type Choice = { category_id: number | null; skip: boolean };
type RowFilter = 'all' | 'review' | 'skipped';

/** Upload a bank statement PDF, review what each line becomes, then import it. */
export default function StatementImportModal({
  opened,
  onClose,
  onImported,
}: {
  opened: boolean;
  onClose: () => void;
  onImported: (month: string) => void;
}) {
  const [fileName, setFileName] = useState('');
  const [preview, setPreview] = useState<StatementPreview | null>(null);

  const parse = useAppMutation((file: File) => api.previewStatement(file));
  const close = () => {
    setPreview(null);
    parse.reset();
    onClose();
  };
  const choose = (file: File | undefined) => {
    if (!file) return;
    setFileName(file.name);
    parse.mutate(file, { onSuccess: setPreview });
  };

  return (
    <Modal
      opened={opened}
      onClose={close}
      size={preview ? 1040 : 'lg'}
      title={preview ? `Review ${preview.bank} statement · ${monthLabel(preview.month)}` : 'Import bank statement'}
    >
      {preview ? (
        <Review
          key={fileName + preview.period_end}
          preview={preview}
          fileName={fileName}
          onBack={() => setPreview(null)}
          onDone={(month) => {
            close();
            onImported(month);
          }}
        />
      ) : (
        <Picker loading={parse.isPending} onChoose={choose} />
      )}
    </Modal>
  );
}

function Picker({ loading, onChoose }: { loading: boolean; onChoose: (file: File | undefined) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const drop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    onChoose(e.dataTransfer.files[0]);
  };

  return (
    <Stack>
      <UnstyledButton
        className="drop-zone"
        data-over={over || undefined}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
        disabled={loading}
      >
        <Stack align="center" gap="xs" py="xl">
          {loading ? <Loader size="md" /> : <IconFileUpload size={36} stroke={1.5} color="var(--mantine-color-primary-4)" />}
          <Text fw={600}>{loading ? 'Reading statement…' : 'Drop your statement PDF here'}</Text>
          <Text size="sm" c="dimmed">
            or click to choose a file
          </Text>
        </Stack>
      </UnstyledButton>
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        hidden
        onChange={(e) => {
          onChoose(e.currentTarget.files?.[0]);
          e.currentTarget.value = '';
        }}
      />
      <Text size="xs" c="dimmed">
        SoFi checking and savings statements are supported. Nothing is saved until you review the lines and import
        them, and the PDF itself isn't kept.
      </Text>
    </Stack>
  );
}

function Review({
  preview,
  fileName,
  onBack,
  onDone,
}: {
  preview: StatementPreview;
  fileName: string;
  onBack: () => void;
  onDone: (month: string) => void;
}) {
  const [choices, setChoices] = useState<Record<string, Choice>>(() =>
    Object.fromEntries(preview.rows.map((r) => [r.key, { category_id: r.category_id, skip: r.skip }])),
  );
  const [accountIds, setAccountIds] = useState<Record<string, number | null>>(() =>
    Object.fromEntries(preview.accounts.map((a) => [a.key, a.account_id])),
  );
  const [updateBalances, setUpdateBalances] = useState(true);
  const [filter, setFilter] = useState<RowFilter>('all');
  // Phones: the date and category columns fold into the description cell.
  const phone = useMediaQuery('(max-width: 36em)') ?? false;

  const fresh = preview.rows.filter((r) => !r.duplicate);
  const included = fresh.filter((r) => !choices[r.key].skip);
  const missing = included.filter((r) => choices[r.key].category_id == null);
  const income = included.filter((r) => r.amount > 0).reduce((s, r) => s + r.amount, 0);
  const expenses = included.filter((r) => r.amount < 0).reduce((s, r) => s - r.amount, 0);
  const duplicates = preview.rows.length - fresh.length;
  const needsReview = fresh.filter((r) => r.reason === 'Not recognized').length;
  const accountNames = Object.fromEntries(preview.accounts.map((a) => [a.key, a.name]));

  const visible = useMemo(
    () =>
      preview.rows.filter((r) => {
        if (filter === 'review') return !r.duplicate && r.reason === 'Not recognized';
        if (filter === 'skipped') return !r.duplicate && choices[r.key].skip;
        return true;
      }),
    [preview.rows, filter, choices],
  );

  const save = useAppMutation(() =>
    api.importStatement({
      bank: preview.bank,
      file_name: fileName,
      period_start: preview.period_start,
      period_end: preview.period_end,
      accounts: preview.accounts.map((a) => ({
        key: a.key,
        name: a.name,
        beginning: a.beginning,
        ending: a.ending,
        account_id: accountIds[a.key],
      })),
      rows: fresh.map((r) => ({
        key: r.key,
        date: r.date,
        account_key: r.account_key,
        description: r.description,
        amount: r.amount,
        ...choices[r.key],
      })),
      update_balances: updateBalances,
    }),
  );
  const submit = () =>
    save.mutate(undefined, {
      onSuccess: (record) => {
        notifications.show({ message: `Imported ${record.transaction_count} transactions`, color: 'green' });
        onDone(preview.month);
      },
    });

  const setChoice = (key: string, change: Partial<Choice>) =>
    setChoices((c) => ({ ...c, [key]: { ...c[key], ...change } }));

  return (
    <Stack>
      <Text size="sm" c="dimmed">
        {dayjs(preview.period_start).format('MMM D')} – {dayjs(preview.period_end).format('MMM D, YYYY')} · {fileName}
      </Text>

      <SimpleGrid cols={{ base: 1, sm: preview.accounts.length > 1 ? 2 : 1 }}>
        {preview.accounts.map((a) => (
          <AccountCard
            key={a.key}
            account={a}
            accountId={accountIds[a.key]}
            onAccountChange={(id) => setAccountIds((ids) => ({ ...ids, [a.key]: id }))}
          />
        ))}
      </SimpleGrid>
      <Checkbox
        label={`Update the Balance Sheet with these ending balances for ${monthLabel(preview.month)}`}
        checked={updateBalances}
        onChange={(e) => setUpdateBalances(e.currentTarget.checked)}
      />

      {duplicates === preview.rows.length ? (
        <Alert color="gray" icon={<IconCircleCheck size={18} />}>
          This statement has already been imported.
        </Alert>
      ) : (
        <>
          <Group justify="space-between" wrap="wrap" gap="xs">
            <Text size="sm" c="dimmed">
              Transfers between your own accounts are skipped. Your choices are remembered for next month.
            </Text>
            <FilterControl
              label="Show"
              value={filter}
              onChange={(v) => setFilter(v as RowFilter)}
              data={[
                { value: 'all', label: `All ${preview.rows.length}` },
                { value: 'review', label: `Not recognized ${needsReview}` },
                { value: 'skipped', label: `Skipped ${fresh.length - included.length}` },
              ]}
            />
          </Group>
          <Table.ScrollContainer minWidth={phone ? 0 : 760}>
            <Table verticalSpacing={6} highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w={phone ? 36 : 70}>{phone ? '' : 'Import'}</Table.Th>
                  {!phone && <Table.Th w={70}>Date</Table.Th>}
                  <Table.Th>Description</Table.Th>
                  {!phone && <Table.Th w={240}>Category</Table.Th>}
                  <Table.Th ta="right" w={110}>
                    Amount
                  </Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {visible.map((r) => (
                  <ReviewRow
                    key={r.key}
                    row={r}
                    choice={choices[r.key]}
                    accountName={accountNames[r.account_key]}
                    phone={phone}
                    onChange={(change) => setChoice(r.key, change)}
                  />
                ))}
                {visible.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={phone ? 3 : 5}>
                      <Text size="sm" c="dimmed" ta="center" py="md">
                        Nothing here.
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </>
      )}

      <Group justify="space-between" wrap="wrap" className="modal-footer">
        <Text size="sm" className="num">
          <b>{included.length}</b> to import · income {money(income)} · expenses {money(expenses)}
          {duplicates > 0 && <Text span c="dimmed">{` · ${duplicates} already imported`}</Text>}
        </Text>
        <Group gap="xs">
          <Button variant="default" onClick={onBack}>
            Choose another file
          </Button>
          <Button onClick={submit} loading={save.isPending} disabled={fresh.length === 0 || missing.length > 0}>
            {missing.length > 0 ? `Pick ${missing.length} ${missing.length === 1 ? 'category' : 'categories'}` : `Import ${included.length}`}
          </Button>
        </Group>
      </Group>
    </Stack>
  );
}

function AccountCard({
  account,
  accountId,
  onAccountChange,
}: {
  account: PreviewAccount;
  accountId: number | null;
  onAccountChange: (id: number | null) => void;
}) {
  const { data: accounts = [] } = useQuery({ queryKey: ['accounts'], queryFn: () => api.accounts() });
  const options = accounts
    .filter((a) => a.kind === 'asset' && !a.sync_from_holdings)
    .map((a) => ({ value: String(a.id), label: a.name }));
  const off = account.difference != null && Math.abs(account.difference) >= 0.005;

  return (
    <Paper p="sm" className="inset-panel">
      <Group justify="space-between" wrap="wrap" align="flex-start" gap="xs">
        <div>
          <Text fw={600}>{account.name}</Text>
          <Text size="sm" c="dimmed" className="num">
            {money(account.beginning)} → {money(account.ending)}
          </Text>
        </div>
        {account.difference == null ? null : off ? (
          <Badge color="red" variant="light" leftSection={<IconAlertTriangle size={12} />}>
            Off by {money(account.difference)}
          </Badge>
        ) : (
          <Badge color="green" variant="light" leftSection={<IconCircleCheck size={12} />}>
            Every line read
          </Badge>
        )}
      </Group>
      {off && (
        <Text size="xs" c="red.4" mt={4}>
          The lines don&apos;t add up to the ending balance, so some may be missing. Check against the PDF.
        </Text>
      )}
      <Select
        mt="xs"
        label="Balance Sheet account"
        placeholder="Don't link"
        data={options}
        clearable
        value={accountId == null ? null : String(accountId)}
        onChange={(v) => onAccountChange(v == null ? null : Number(v))}
      />
    </Paper>
  );
}

function ReviewRow({
  row,
  choice,
  accountName,
  phone,
  onChange,
}: {
  row: PreviewRow;
  choice: Choice;
  accountName: string;
  phone: boolean;
  onChange: (change: Partial<Choice>) => void;
}) {
  const off = row.duplicate || choice.skip;
  const kind = row.amount > 0 ? 'income' : 'expense';
  const category = !off && (
    <CategorySelect
      label={null}
      aria-label="Category"
      mt={phone ? 6 : undefined}
      kind={kind}
      value={choice.category_id}
      onChange={(id) => onChange({ category_id: id })}
      error={choice.category_id == null}
      comboboxProps={{ withinPortal: true }}
    />
  );
  return (
    <Table.Tr className={off ? 'row-muted' : undefined}>
      <Table.Td className="keep-opaque">
        <Checkbox
          aria-label={`Import ${row.description}`}
          checked={!off}
          disabled={row.duplicate}
          onChange={(e) => onChange({ skip: !e.currentTarget.checked })}
        />
      </Table.Td>
      {!phone && <Table.Td className="num">{dayjs(row.date).format('MMM D')}</Table.Td>}
      <Table.Td>
        <Text size="sm">{row.description}</Text>
        <Text size="xs" c="dimmed">
          {phone && `${dayjs(row.date).format('MMM D')} · `}
          {accountName}
          {row.section.includes('Vault') ? ` · ${row.section}` : ''} · {row.bank_type} ·{' '}
          {row.duplicate ? 'Already imported' : choice.skip && !row.skip ? 'Skipped' : row.reason}
        </Text>
        {phone && category}
      </Table.Td>
      {!phone && <Table.Td>{category}</Table.Td>}
      <Table.Td ta="right" className="num" fw={500} style={{ whiteSpace: 'nowrap' }} valign="top">
        {row.amount > 0 ? '+' : '−'}
        {money(Math.abs(row.amount))}
      </Table.Td>
    </Table.Tr>
  );
}
