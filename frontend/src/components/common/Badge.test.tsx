import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Badge } from './Badge';

describe('Badge component', () => {
  it('renders badge label correctly', () => {
    render(<Badge variant="emerald">FULLY GROUNDED</Badge>);
    expect(screen.getByText('FULLY GROUNDED')).toBeInTheDocument();
  });
});
