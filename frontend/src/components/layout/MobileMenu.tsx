import { useState } from 'react';
import { Link } from 'react-router-dom';

import GitHubIcon from '@/components/icons/GitHubIcon';
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
}

const MobileMenu = ({
  navItems,
  selectedSimulationIds,
  isAuthenticated,
  user,
  loginWithGithub,
}: MobileMenuProps) => {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        className="md:hidden flex items-center justify-center h-9 w-9 rounded-md hover:bg-accent"
        onClick={() => setOpen(true)}
      >
        <svg
          className="h-5 w-5 text-foreground"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm md:hidden">
          <div className="absolute right-0 top-0 h-full w-64 bg-white shadow-xl p-4 flex flex-col gap-4">
            <button
              className="self-end mb-2 p-2 rounded hover:bg-accent"
              onClick={() => setOpen(false)}
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
              <div className="flex items-center gap-3 p-2 border rounded-md">
                <Avatar>
                  <AvatarImage src="/avatars/default.jpg" />
                  <AvatarFallback>{user?.email?.[0]?.toUpperCase()}</AvatarFallback>
                </Avatar>
                <span
                  className="text-sm font-medium truncate max-w-[140px] sm:max-w-[180px] md:max-w-[220px]"
                  title={user?.full_name || user?.email}
                >
                  {user?.full_name || user?.email}
                </span>
              </div>
            )}

            <div className="mt-4 flex flex-col gap-2">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  to={item.href}
                  className="px-2 py-1.5 text-sm rounded hover:bg-accent"
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
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default MobileMenu;
