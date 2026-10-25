import { Box, Button, Group, Modal, Paper, SimpleGrid, Stack, Table, Text, Textarea, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconPlus } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { api } from '../api';
import { EmptyState, PageHeader, SectionCard, useAppMutation } from '../components/common';
import { money, signedMoney } from '../format';
import type { Company, CompanyInput, CompanyListItem } from '../types';

/** "60%" / "33.3333%": up to four decimals, no trailing zeros. */
export const equity = (n: number) => `${Number(n.toFixed(4))}%`;

export default function CompaniesPage() {
  const [adding, setAdding] = useState(false);
  const { data: companies = [], isLoading } = useQuery({ queryKey: ['companies'], queryFn: () => api.companies() });
  const year = companies[0]?.year ?? new Date().getFullYear();

  return (
    <>
      <PageHeader
        title="Companies"
        description="Each business's income, expenses, member contributions, and ownership."
        actions={
          <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
            Add company
          </Button>
        }
      />

      {companies.length > 1 && (
        <Box mb="xl">
          <OwnerShares companies={companies} year={year} />
        </Box>
      )}

      {isLoading ? null : companies.length === 0 ? (
        <Paper p="1.1rem">
          <EmptyState
            message="Add a company to track its income, expenses, what each member has put in, and who owns how much."
            action={
              <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setAdding(true)}>
                Add company
              </Button>
            }
          />
        </Paper>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="lg">
          {companies.map((c) => (
            <CompanyTile key={c.id} company={c} />
          ))}
        </SimpleGrid>
      )}

      <Modal opened={adding} onClose={() => setAdding(false)} title="Add company">
        {adding && <CompanyForm company={null} onDone={() => setAdding(false)} />}
      </Modal>
    </>
  );
}

/**
 * Each owner's share of profit across the companies they're in (net × ownership, matched by name).
 * Adding up the companies' own profits would mix stakes held by different people.
 */
function OwnerShares({ companies, year }: { companies: CompanyListItem[]; year: number }) {
  const owners = new Map<string, { stakes: string[]; share: number }>();
  for (const c of companies) {
    for (const m of c.members) {
      const owner = owners.get(m.name) ?? { stakes: [], share: 0 };
      owner.stakes.push(`${c.name} ${equity(m.equity_percent)}`);
      owner.share += (c.net * m.equity_percent) / 100;
      owners.set(m.name, owner);
    }
  }
  if (owners.size === 0) return null;
  return (
    <SectionCard title={`Share of profit by owner · ${year}`}>
      <Table.ScrollContainer minWidth={480}>
        <Table verticalSpacing={6} highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Owner</Table.Th>
              <Table.Th>Stakes</Table.Th>
              <Table.Th ta="right">Share of profit</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {[...owners].map(([name, o]) => (
              <Table.Tr key={name}>
                <Table.Td fw={500}>{name}</Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed">
                    {o.stakes.join(' · ')}
                  </Text>
                </Table.Td>
                <Table.Td ta="right" className="num" fw={500}>
                  {signedMoney(Math.round(o.share * 100) / 100)}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Text size="xs" c="dimmed" mt="sm">
        Each company's {year} net profit times the owner's share of it, added up for owners in more than one company
        (matched by name). It's an entitlement on paper, not money paid out.
      </Text>
    </SectionCard>
  );
}

function CompanyTile({ company: c }: { company: CompanyListItem }) {
  const figure = (label: string, value: string) => (
    <div>
      <Text className="label-sm">{label}</Text>
      <Text size="sm" fw={600} mt={4} className="num">
        {value}
      </Text>
    </div>
  );
  return (
    <Paper component={Link} to={`/companies/${c.id}`} p="1.1rem" h="100%" className="tile-link">
      <Stack gap="md">
        <div>
          <Text className="headline" fw={700} size="lg" lh={1.25}>
            {c.name}
          </Text>
          {/* Always one line, blank when there's no description, so the figures line up across tiles. */}
          <Text size="sm" c="dimmed" lineClamp={1} title={c.description ?? undefined}>
            {c.description || '\u00a0'}
          </Text>
        </div>
        <SimpleGrid cols={3} spacing="sm">
          {figure(`Income ${c.year}`, money(c.income))}
          {figure('Expenses', money(c.expenses))}
          {figure('Net', signedMoney(c.net))}
        </SimpleGrid>
        <div>
          <Text className="label-sm">Owners</Text>
          <Text size="sm" mt={4}>
            {c.members.length === 0
              ? 'No members yet'
              : c.members.map((m) => `${m.name} ${equity(m.equity_percent)}`).join(' · ')}
          </Text>
        </div>
        <Text size="xs" c="dimmed" className="num">
          All time: {money(c.contributions_total)} contributed · {money(c.distributions_total)} distributed
        </Text>
      </Stack>
    </Paper>
  );
}

/** Add or edit a company's name and description. A new company opens its page once saved. */
export function CompanyForm({ company, onDone }: { company: Company | null; onDone: () => void }) {
  const navigate = useNavigate();
  const form = useForm({
    initialValues: { name: company?.name ?? '', description: company?.description ?? '' },
    validate: { name: (v) => (v.trim() ? null : 'Required') },
  });
  const save = useAppMutation(
    (body: CompanyInput) => (company ? api.updateCompany(company.id, body) : api.createCompany(body)),
    company ? 'Company updated' : 'Company added',
  );
  return (
    <form
      onSubmit={form.onSubmit((v) =>
        save.mutate(
          { name: v.name.trim(), description: v.description.trim() || null },
          {
            onSuccess: (saved) => {
              onDone();
              if (!company) navigate(`/companies/${saved.id}`);
            },
          },
        ),
      )}
    >
      <Stack>
        <TextInput label="Company name" placeholder="Acme LLC" data-autofocus {...form.getInputProps('name')} />
        <Textarea
          label="Description"
          placeholder="What the business does"
          autosize
          minRows={2}
          maxRows={5}
          {...form.getInputProps('description')}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onDone}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            {company ? 'Save' : 'Add company'}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
