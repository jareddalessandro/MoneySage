import { Alert, Anchor, Container, Group, List, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconArrowLeft } from '@tabler/icons-react';
import dayjs from 'dayjs';
import { useEffect, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import type { Site } from '../types';
import { SiteFooter } from './Landing';

// Drafts written for how MoneySage actually works. They aren't legal advice: have them reviewed before
// opening sign-ups. When they change in a way people should agree to again, bump TERMS_VERSION in
// backend/app/legal.py (its date is the "last updated" shown here).

function who(site: Site | undefined) {
  return site?.operator_name ?? 'the operator of this site';
}

function Contact({ site }: { site: Site | undefined }) {
  return site?.contact_email ? <Anchor href={`mailto:${site.contact_email}`}>{site.contact_email}</Anchor> : <>the operator</>;
}

function LegalLayout({ title, site, signedIn, children }: { title: string; site: Site | undefined; signedIn: boolean; children: ReactNode }) {
  const missing = site && site.auth_mode === 'google' && !(site.operator_name && site.contact_email);
  // Links here come from the foot of other pages; start at the top.
  useEffect(() => window.scrollTo(0, 0), []);
  return (
    <>
      <Container size="sm" px="md" py="xl">
        <Stack gap="lg">
          {!signedIn && (
            <Anchor component={Link} to="/" size="sm" className="hit-44">
              <Group gap={4}>
                <IconArrowLeft size={14} /> MoneySage
              </Group>
            </Anchor>
          )}
          <div>
            <Title order={1} fz="1.75rem" lts="-0.01em">
              {title}
            </Title>
            {site && (
              <Text size="sm" c="dimmed" mt={4}>
                Last updated {dayjs(site.terms_version).format('MMMM D, YYYY')}
              </Text>
            )}
          </div>
          {missing && (
            <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={18} />}>
              Draft: whoever runs this site hasn't filled in their name and contact address yet (OPERATOR_NAME and
              CONTACT_EMAIL).
            </Alert>
          )}
          <Stack gap="md">
            {children}
          </Stack>
        </Stack>
      </Container>
      {!signedIn && <SiteFooter site={site} />}
    </>
  );
}

function H({ children }: { children: ReactNode }) {
  return (
    <Title order={2} fz="1.15rem" mt="md">
      {children}
    </Title>
  );
}

function P({ children }: { children: ReactNode }) {
  return <Text size="sm">{children}</Text>;
}

function Items({ children }: { children: ReactNode }) {
  return (
    <List size="sm" spacing={6}>
      {children}
    </List>
  );
}

export function PrivacyPage({ site, signedIn = false }: { site: Site | undefined; signedIn?: boolean }) {
  return (
    <LegalLayout title="Privacy Policy" site={site} signedIn={signedIn}>
      <P>
        MoneySage is a personal and family finance tracker run by {who(site)} ("we"). This policy explains what we
        collect, why, who can see it, and the choices you have. The short version: your data is used to run
        MoneySage for you and the people you share with, and for nothing else. We don't sell it and we don't show
        ads.
      </P>

      <H>What we collect</H>
      <Items>
        <List.Item>
          <b>Your Google account basics</b>, when you sign in with Google: your name, email address, profile picture
          and Google's account ID. We never see your Google password.
        </List.Item>
        <List.Item>
          <b>What you put in MoneySage</b>: budgets, transactions, account balances, investment holdings, credit
          card reference details, company records, notes and categories.
        </List.Item>
        <List.Item>
          <b>Bank statements you upload.</b> A statement PDF is read to pull out its transactions and balances, then
          discarded. The file itself is never stored. The transactions you choose to import are stored.
        </List.Item>
        <List.Item>
          <b>Sharing details</b>: the email addresses you invite, and who has access to what.
        </List.Item>
        <List.Item>
          <b>Technical data</b>: a sign-in cookie, the browser you signed in with, and server logs (IP address,
          time, and the page or action requested) used to keep the service secure and working.
        </List.Item>
      </Items>
      <P>
        MoneySage never asks for bank logins and never connects to your bank. Please don't enter card numbers,
        security codes, account passwords or government ID numbers anywhere in it.
      </P>

      <H>How we use it</H>
      <Items>
        <List.Item>To provide MoneySage: show your finances, compute totals, refresh investment prices, and produce the statements and exports you ask for.</List.Item>
        <List.Item>To let the people you invite see or edit what you've shared with them.</List.Item>
        <List.Item>To keep the service secure: prevent abuse, investigate problems, and protect accounts.</List.Item>
        <List.Item>To contact you about your account or important changes to MoneySage.</List.Item>
      </Items>
      <P>
        We don't sell your personal information, share it for advertising, use it to build marketing profiles, or
        use it to train AI models.
      </P>

      <H>Who can see it</H>
      <Items>
        <List.Item>
          <b>You, and the people you share with.</b> A household and each company are shared separately, only by
          their owner, and only with the people the owner invites, as editors or view-only.
        </List.Item>
        <List.Item>
          <b>Service providers that run MoneySage for us</b>, only as needed to do so: our hosting provider (servers
          and storage in the United States), Google (to sign you in), and a market data provider, which receives
          the ticker symbols being priced but not who holds them.
        </List.Item>
        <List.Item>
          <b>When the law requires it</b>, such as a valid court order, or to protect the rights and safety of our
          users or others.
        </List.Item>
        <List.Item>
          <b>If MoneySage changes hands</b>, your data would move with it under this policy, and we'd tell you
          first.
        </List.Item>
      </Items>
      <P>
        MoneySage's use of information received from Google APIs adheres to the{' '}
        <Anchor href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noopener noreferrer">
          Google API Services User Data Policy
        </Anchor>
        , including the Limited Use requirements.
      </P>

      <H>Cookies</H>
      <P>
        MoneySage uses two cookies, both needed for sign-in: a short-lived one while you sign in with Google, and
        one that keeps you signed in. There are no advertising or analytics cookies and no third-party trackers.
      </P>

      <H>Security</H>
      <P>
        Data is sent over encrypted connections (HTTPS). Each request can reach only the households and companies
        you have access to, and the database enforces the same separation. Sign-in sessions are stored as one-way
        hashes. No system is perfectly secure, though, so we can't promise that your information will never be
        accessed improperly. If a breach affects your data, we'll tell you as the law requires.
      </P>

      <H>How long we keep it</H>
      <P>
        We keep your data while your account is open. When you ask us to delete your account, we delete your data,
        including households and companies you own (people you shared them with lose access), within 30 days,
        including from backups. Server logs are kept for a limited time for security.
      </P>

      <H>Your choices and rights</H>
      <Items>
        <List.Item>
          <b>Export</b>: download everything you own as a file at any time, from Export &amp; import.
        </List.Item>
        <List.Item>
          <b>Correct or delete</b>: edit or delete records yourself, or ask us to delete your account.
        </List.Item>
        <List.Item>
          <b>Sharing</b>: remove anyone's access to what you own, or leave something shared with you.
        </List.Item>
        <List.Item>
          Depending on where you live (for example in California or the European Union), you may have further
          rights, such as to know what we hold about you or to object to how it's used. Contact us and we'll help.
          We won't treat you differently for using them.
        </List.Item>
      </Items>

      <H>Children</H>
      <P>MoneySage is for adults. It isn't meant for anyone under 18, and we don't knowingly collect children's information.</P>

      <H>Changes</H>
      <P>
        If we change this policy in a way that matters, we'll update the date above and ask you to review and agree
        to it the next time you use MoneySage.
      </P>

      <H>Contact</H>
      <P>
        Questions or requests about your data: <Contact site={site} />.
      </P>
    </LegalLayout>
  );
}

export function TermsPage({ site, signedIn = false }: { site: Site | undefined; signedIn?: boolean }) {
  return (
    <LegalLayout title="Terms of Service" site={site} signedIn={signedIn}>
      <P>
        These terms are an agreement between you and {who(site)} ("we") about your use of MoneySage. By creating an
        account or using MoneySage, you agree to them and to the{' '}
        <Anchor component={Link} to="/privacy">
          Privacy Policy
        </Anchor>
        .
      </P>

      <H>1. Who can use MoneySage</H>
      <P>You must be at least 18 and able to agree to these terms. Each account is for one person.</P>

      <H>2. Your account</H>
      <P>
        You sign in with your Google account. Keep it secure: you're responsible for what happens under your
        account. Tell us right away if you think someone else has used it.
      </P>

      <H>3. Your data</H>
      <P>
        What you put into MoneySage stays yours. You give us permission to store, process and display it only as
        needed to run MoneySage for you and the people you share with. You can export it at any time. Keep your own
        exports of anything you can't afford to lose: we work to protect your data but can't guarantee it will never
        be lost.
      </P>

      <H>4. Sharing</H>
      <P>
        When you share a household or company, the people you invite can see it, and editors can change it. You're
        responsible for who you invite and what you share. You can remove access at any time; changes others made
        while they had access stay.
      </P>

      <H>5. Acceptable use</H>
      <Items>
        <List.Item>Don't break the law with MoneySage, or use it to store other people's information without their permission.</List.Item>
        <List.Item>Don't enter card numbers, security codes, passwords or government ID numbers.</List.Item>
        <List.Item>Don't try to get into other people's data, probe or overload the service, or get around its limits or security.</List.Item>
        <List.Item>Don't copy, resell or scrape MoneySage, or use it to build a competing service.</List.Item>
      </Items>

      <H>6. Not financial advice</H>
      <P>
        MoneySage is a record-keeping tool. It isn't a bank, doesn't hold or move money, and doesn't give financial,
        investment, tax or legal advice. Figures can be wrong or out of date: investment prices come from
        third-party sources and may be delayed or inaccurate, and transactions read from statements may be misread.
        Check anything important against your bank and brokerage records, and talk to a qualified professional
        before making financial decisions.
      </P>

      <H>7. Price</H>
      <P>
        MoneySage is free during early access. We may introduce paid plans later. We'll tell you before anything
        you use starts to cost money, and you won't be charged unless you choose a paid plan.
      </P>

      <H>8. Changes and availability</H>
      <P>
        We may change, add or remove features, and MoneySage may sometimes be unavailable. If we shut MoneySage down,
        we'll give you reasonable notice and time to export your data.
      </P>

      <H>9. Ending your use</H>
      <P>
        You can stop using MoneySage and ask us to delete your account at any time. We may suspend or close accounts
        that break these terms or put the service or other people at risk, with notice where we reasonably can.
      </P>

      <H>10. Disclaimers</H>
      <P>
        MoneySage is provided "as is" and "as available", without warranties of any kind, express or implied,
        including fitness for a particular purpose, accuracy, and uninterrupted or error-free operation, to the
        fullest extent the law allows.
      </P>

      <H>11. Limitation of liability</H>
      <P>
        To the fullest extent the law allows, we aren't liable for indirect, incidental, special, consequential or
        punitive damages, or for lost profits, data or financial losses arising from your use of MoneySage or
        decisions made with it. Our total liability for any claim about MoneySage is limited to the greater of what
        you paid us in the 12 months before the claim or US$50. Some places don't allow these limits, so they may
        not all apply to you.
      </P>

      <H>12. Governing law</H>
      <P>
        These terms are governed by the laws of {site?.governing_law ?? 'the place where the operator is based'},
        without regard to conflict-of-law rules, except where the law where you live requires otherwise.
      </P>

      <H>13. Changes to these terms</H>
      <P>
        If we change these terms in a way that matters, we'll update the date above and ask you to agree to the new
        version before you continue using MoneySage.
      </P>

      <H>14. Contact</H>
      <P>
        Questions about these terms: <Contact site={site} />.
      </P>
    </LegalLayout>
  );
}
