import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { GitHubIcon } from '@/components/icons/GitHubIcon';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import type { User } from '@/types/user';

interface NavItem {
  label: string;
  href: string;
}

interface MobileMenuProps {
  navItems: NavItem[];
  selectedSimulationIds: string[];
  isAuthenticated: boolean;
  user?: User | null;
  loginWithGithub: () => void;
  logout: () => void;
}

export const MobileMenu = ({
  navItems,
  selectedSimulationIds,
  isAuthenticated,
  user,
  loginWithGithub,
  logout,
}: MobileMenuProps) => {
  const [open, setOpen] = useState(false);

  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const menu = menuRef.current;
    if (!menu) return;

    const focusable = menu.querySelectorAll<HTMLElement>(
      'a, button, input, textarea, select, [tabindex]:not([tabindex="-1"])',
    );

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    first?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setOpen(false);
        return;
      }

      if (e.key === 'Tab' && focusable.length > 0) {
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  useEffect(() => {
    if (!open) {
      buttonRef.current?.focus();
    }
  }, [open]);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="mobile-menu"
        className="md:hidden flex items-center justify-center h-9 w-9 rounded-md hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring"
        onClick={() => setOpen(true)}
      >
        <svg
          className="h-5 w-5 text-foreground"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
        <span className="sr-only">Open menu</span>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm md:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Mobile navigation"
          onClick={() => setOpen(false)}
        >
          <div
            id="mobile-menu"
            ref={menuRef}
            className="absolute right-0 top-0 h-full w-64 bg-white shadow-xl p-4 flex flex-col gap-4"
          >
            <button
              type="button"
              className="self-end mb-2 p-2 rounded hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring"
              onClick={() => setOpen(false)}
              aria-label="Close menu"
            >
              ✕
            </button>

            {!isAuthenticated ? (
              <Button
                onClick={loginWithGithub}
                className="flex items-center gap-2 bg-[#24292f] hover:bg-[#1e2227] text-white w-full"
              >
                <GitHubIcon className="h-4 w-4" />
                Log in with GitHub
              </Button>
            ) : (
              <div className="flex flex-col gap-2 p-2 border rounded-md">
                <div className="flex items-center gap-3">
                  <Avatar>
                    <AvatarImage src="/avatars/default.jpg" />
                    <AvatarFallback>{user?.email?.[0]?.toUpperCase()}</AvatarFallback>
                  </Avatar>
                  <span
                    className="text-sm font-medium truncate max-w-[160px]"
                    title={user?.full_name || user?.email}
                  >
                    {user?.full_name || user?.email}
                  </span>
                </div>
                <button
                  className="self-start text-xs text-destructive hover:underline"
                  onClick={async () => {
                    setOpen(false);
                    await logout();
                  }}
                >
                  Log out
                </button>
              </div>
            )}

            <nav className="mt-4 flex flex-col gap-2">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  to={item.href}
                  className="px-2 py-1.5 text-sm rounded hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring"
                  onClick={() => setOpen(false)}
                >
                  {item.label}
                  {item.label === 'Compare' && selectedSimulationIds.length > 0 && (
                    <span className="ml-2 inline-block text-xs bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded">
                      {selectedSimulationIds.length}
                    </span>
                  )}
                </Link>
              ))}
            </nav>
          </div>
        </div>
      )}
    </>
  );
};
