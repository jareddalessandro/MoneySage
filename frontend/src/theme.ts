import { createTheme, type CSSVariablesResolver, type MantineColorsTuple } from '@mantine/core';

/**
 * "Quantitative Archive" design tokens (see DESIGN.md). Dark only.
 * The spec names surface, surface_container_low/high, primary(_container), secondary and
 * tertiary_container; the remaining tones are filled in from the same Material 3 scheme.
 */
export const tokens = {
  surface: '#10131a',
  surfaceContainerLow: '#191c22',
  surfaceContainer: '#1d2026',
  surfaceContainerHigh: '#272a31',
  surfaceContainerHighest: '#32353c',
  surfaceVariant: '#32353c',
  onSurface: '#e1e2eb',
  onSurfaceVariant: '#bcc8cf',
  outline: '#87939a',
  outlineVariant: '#3c494e',
  primary: '#4cd6ff',
  primaryContainer: '#009dc1',
  onPrimary: '#003543',
  secondary: '#40e56c',
  tertiaryContainer: '#ff5353',
};

// Precision blue, built around primary (index 4) and primary_container (index 7).
const sky: MantineColorsTuple = [
  '#e3f8ff',
  '#c4f0ff',
  '#9de6ff',
  '#74ddff',
  '#4cd6ff',
  '#2ec8f4',
  '#12b4e0',
  '#009dc1',
  '#007f9d',
  '#00627a',
];

// Mantine reads dark[0] for text, [2] for dimmed, [4] for borders, [5] for hover,
// [6] for input fills, and [7] for the page background.
const dark: MantineColorsTuple = [
  tokens.onSurface,
  tokens.onSurfaceVariant,
  '#9aa4ab',
  '#6f7a80',
  tokens.outlineVariant,
  tokens.surfaceContainerHighest,
  tokens.surfaceContainer,
  tokens.surface,
  '#0b0e14',
  '#07090d',
];

const HEADING_FONT = '"Manrope Variable", system-ui, sans-serif';

export const theme = createTheme({
  primaryColor: 'sky',
  primaryShade: 4,
  colors: { sky, dark },
  autoContrast: true,
  luminanceThreshold: 0.35,
  fontFamily: '"Inter Variable", system-ui, -apple-system, "Segoe UI", sans-serif',
  headings: { fontFamily: HEADING_FONT, fontWeight: '700' },
  defaultGradient: { from: tokens.primary, to: tokens.primaryContainer, deg: 135 },
  radius: { xs: '0.25rem', sm: '0.375rem', md: '0.5rem', lg: '0.5rem', xl: '0.75rem' },
  defaultRadius: 'md',
  shadows: { md: '0px 12px 32px rgba(4, 6, 10, 0.4)', lg: '0px 12px 32px rgba(4, 6, 10, 0.4)' },
  other: { headingFont: HEADING_FONT },
  components: {
    // Primary CTAs get the primary → primary_container gradient (text color set in styles.css).
    Button: { defaultProps: { variant: 'gradient', radius: 'xl' } },
    Card: { defaultProps: { radius: 'md', withBorder: false } },
    Paper: { defaultProps: { radius: 'md', withBorder: false } },
    // No-line rule: rows are separated by hover tone, not 1px dividers.
    Table: { defaultProps: { withRowBorders: false, highlightOnHover: true } },
    AppShell: { defaultProps: { withBorder: false } },
    Modal: { defaultProps: { radius: 'md', shadow: 'md', overlayProps: { backgroundOpacity: 0.5, blur: 2 } } },
    Popover: { defaultProps: { shadow: 'md' } },
    Menu: { defaultProps: { shadow: 'md' } },
    Tooltip: { defaultProps: { color: 'dark.5' } },
  },
});

export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {},
  light: {},
  dark: {
    '--mantine-color-body': tokens.surface,
    '--mantine-color-text': tokens.onSurface,
    '--mantine-color-dimmed': '#9aa4ab',
    '--mantine-color-default': tokens.surfaceContainer,
    '--mantine-color-default-hover': tokens.surfaceContainerHighest,
    '--mantine-color-default-border': tokens.outlineVariant,
  },
});
