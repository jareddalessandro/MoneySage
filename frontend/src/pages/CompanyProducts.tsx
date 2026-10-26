import { Button, Group, Stack, Table, Text, Textarea, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconPencil, IconPlus, IconTrash } from '@tabler/icons-react';

import { api } from '../api';
import { confirmDelete, EmptyState, RowActions, SectionCard, useAppMutation } from '../components/common';
import { money, percent, signedMoney } from '../format';
import type { Company, CompanyProduct, CompanyProductInput, CompanySummary } from '../types';

/** Income, cost of revenue, other expenses and net for each product in the year. */
export function Products({
  company,
  summary,
  onAdd,
  onEdit,
}: {
  company: Company;
  summary: CompanySummary | undefined;
  onAdd: () => void;
  onEdit: (product: CompanyProduct) => void;
}) {
  const remove = useAppMutation((productId: number) => api.deleteCompanyProduct(company.id, productId), 'Product deleted');
  const rows = summary?.products ?? [];

  return (
    <SectionCard
      title={summary ? `Products · ${summary.year}` : 'Products'}
      actions={
        company.products.length > 0 && (
          <Button size="xs" variant="default" leftSection={<IconPlus size={14} />} onClick={onAdd}>
            Add product
          </Button>
        )
      }
    >
      {company.products.length === 0 ? (
        <EmptyState
          message="Optional. Add each product (like each app) to see its own income, costs, and profit, then tag entries with it."
          action={
            <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={onAdd}>
              Add product
            </Button>
          }
        />
      ) : (
        <>
          <Table.ScrollContainer minWidth={560} className="phone-fit">
            <Table verticalSpacing={6} highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Product</Table.Th>
                  <Table.Th ta="right" className="hide-xs">
                    Income
                  </Table.Th>
                  <Table.Th ta="right" className="hide-xs">
                    Cost of revenue
                  </Table.Th>
                  <Table.Th ta="right" className="hide-xs">
                    Other expenses
                  </Table.Th>
                  <Table.Th ta="right">Net</Table.Th>
                  <Table.Th w={70} />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.map((r) => {
                  const product = company.products.find((p) => p.id === r.product_id);
                  return (
                    <Table.Tr key={r.product_id ?? 'none'}>
                      <Table.Td>
                        <Text size="sm" fw={500} c={product ? undefined : 'dimmed'}>
                          {r.name}
                        </Text>
                        {product?.description && (
                          <Text size="xs" c="dimmed" lineClamp={1}>
                            {product.description}
                          </Text>
                        )}
                        <Text size="xs" c="dimmed" className="show-xs num">
                          Income {money(r.income)} · cost of revenue {money(r.cost_of_revenue)} · other{' '}
                          {money(r.other_expenses)}
                        </Text>
                      </Table.Td>
                      <Table.Td ta="right" className="num hide-xs">
                        {money(r.income)}
                      </Table.Td>
                      <Table.Td ta="right" className="num hide-xs">
                        {money(r.cost_of_revenue)}
                      </Table.Td>
                      <Table.Td ta="right" className="num hide-xs">
                        {money(r.other_expenses)}
                      </Table.Td>
                      <Table.Td ta="right" className="num">
                        <Text size="sm" fw={600} span>
                          {signedMoney(r.net)}
                        </Text>
                        {r.income > 0 && (
                          <Text size="xs" c="dimmed">
                            {percent(r.net / r.income)} margin
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        {product && (
                          <RowActions
                            label={`Actions for ${product.name}`}
                            actions={[
                              { label: `Edit ${product.name}`, icon: <IconPencil size={16} />, onClick: () => onEdit(product) },
                              {
                                label: `Delete ${product.name}`,
                                icon: <IconTrash size={16} />,
                                color: 'red',
                                onClick: () => confirmDelete(`product "${product.name}"`, () => remove.mutate(product.id)),
                              },
                            ]}
                          />
                        )}
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Text size="xs" c="dimmed" mt="sm">
            Cost of revenue is revenue-share payments and the platform fees those shares are calculated after.
            Untagged income and expenses show as "No product".
          </Text>
        </>
      )}
    </SectionCard>
  );
}

export function ProductForm({
  companyId,
  product,
  onDone,
}: {
  companyId: number;
  product: CompanyProduct | null;
  onDone: () => void;
}) {
  const form = useForm({
    initialValues: { name: product?.name ?? '', description: product?.description ?? '' },
    validate: { name: (v) => (v.trim() ? null : 'Required') },
  });
  const save = useAppMutation(
    (body: CompanyProductInput) =>
      product ? api.updateCompanyProduct(companyId, product.id, body) : api.createCompanyProduct(companyId, body),
    product ? 'Product updated' : 'Product added',
  );
  return (
    <form
      onSubmit={form.onSubmit((v) =>
        save.mutate({ name: v.name.trim(), description: v.description.trim() || null }, { onSuccess: onDone }),
      )}
    >
      <Stack>
        <TextInput label="Name" placeholder="e.g. the app's name" data-autofocus {...form.getInputProps('name')} />
        <Textarea label="Description" autosize minRows={1} maxRows={4} {...form.getInputProps('description')} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onDone}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            {product ? 'Save' : 'Add product'}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
