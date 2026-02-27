import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';

const buttonVariants = cva(
  'inline-flex items-center cursor-pointer justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default:
          'bg-primary text-primary-foreground hover:bg-primary/90',
        foreground:
          'bg-foreground text-background hover:bg-foreground/90',
        background:
          'bg-background text-foreground hover:bg-background/90',
        destructive:
          'bg-destructive text-destructive-foreground hover:bg-destructive/80',
        'destructive-foreground':
          'border border-border bg-background hover:bg-destructive/15 text-destructive',
        outline:
          'border border-border bg-transparent hover:bg-accent/50 text-foreground',
        secondary:
          'bg-secondary text-secondary-foreground border border-secondary-border',
        text: 'bg-transparent rounded-none opacity-100 hover:opacity-75',
        ghost: 'bg-transparent hover:bg-accent text-foreground',
        link: 'text-primary underline-offset-4 hover:underline !p-0 !h-auto',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm:      'h-7 rounded-sm px-3 text-xs',
        lg:      'h-10 px-6',
        icon:    'size-7 rounded-sm',
        text:    'p-0 h-auto',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props}
    />
  ),
);
Button.displayName = 'Button';

export { buttonVariants };
