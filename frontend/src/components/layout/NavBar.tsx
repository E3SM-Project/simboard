import { ChevronDown, LogOut } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { useAuth } from '@/auth/hooks/useAuth';
import { GitHubIcon } from '@/components/icons/GitHubIcon';
import { MobileMenu } from '@/components/layout/MobileMenu';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

const navItems = [
  { label: 'Home', href: '/', description: 'Overview and featured simulations' },
  { label: 'Browse', href: '/browse', description: 'Guided discovery with filters' },
  { label: 'Compare', href: '/compare', description: 'Side-by-side view of selected runs' },
  {
    label: 'All Simulations',
    href: '/simulations',
    description: 'Complete catalog in a sortable table',
  },
  { label: 'Upload', href: '/upload', description: 'Add a new simulation to the catalog' },
  { label: 'Docs', href: '/docs', description: 'Guides and references for using the viewer' },
];

interface NavBarProps {
  selectedSimulationIds: string[];
}

export const NavBar = ({ selectedSimulationIds }: NavBarProps) => {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const { user, isAuthenticated, loginWithGithub, logout, loading } = useAuth();

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [open]);

  return (
    <header className="w-full bg-white border-b">
      <div className="mx-auto flex max-w-[1440px] items-center justify-between px-4 py-3 md:px-6">
        <div className="flex items-center gap-4">
          {/* Logo */}
          <Link to="/" className="text-xl font-bold flex items-center gap-2">
            <span className="text-muted-foreground">🔬🌍</span>
            SimBoard
          </Link>
        </div>

        <nav className="hidden md:flex gap-3 ml-6">
          {navItems.map((item) => {
            const isCompare = item.label === 'Compare';
            const isActive = location.pathname === item.href;

            return (
              <TooltipProvider delayDuration={150} key={item.href}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Link
                      to={item.href}
                      className={cn(
                        'text-sm font-medium text-muted-foreground hover:text-foreground transition border-b-2 border-transparent px-2 py-1 rounded flex items-center gap-1',
                        isActive && 'text-foreground border-foreground font-semibold',
                      )}
                    >
                      {item.label}

                      {isCompare && selectedSimulationIds.length > 0 && (
                        <span className="ml-1 inline-flex items-center justify-center px-1.5 py-0.5 text-xs font-semibold rounded-full bg-blue-100 text-blue-800">
                          {selectedSimulationIds.length}
                        </span>
                      )}
                    </Link>
                  </TooltipTrigger>
                  <TooltipContent className="bg-gray-900 text-white px-3 py-2 rounded shadow-lg text-xs">
                    {item.description}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            );
          })}
        </nav>

        <div className="flex items-center gap-3" ref={dropdownRef}>
          <MobileMenu
            navItems={navItems}
            selectedSimulationIds={selectedSimulationIds}
            isAuthenticated={isAuthenticated}
            user={user}
            loginWithGithub={loginWithGithub}
            logout={logout}
          />

          {loading ? (
            <span className="hidden md:block text-sm text-muted-foreground">Loading…</span>
          ) : !isAuthenticated ? (
            <Button
              onClick={loginWithGithub}
              className="hidden md:flex items-center gap-2 bg-[#24292f] hover:bg-[#1e2227] text-white px-4 py-2 rounded-md transition"
            >
              <GitHubIcon className="h-4 w-4" />
              <span>Log in</span>
            </Button>
          ) : (
            <DropdownMenu open={open} onOpenChange={setOpen}>
              <DropdownMenuTrigger asChild>
                <button className="hidden md:flex items-center gap-2 rounded-md px-2 py-1 hover:bg-accent hover:text-accent-foreground transition">
                  <Avatar className="h-8 w-8">
                    <AvatarImage src="/avatars/default.jpg" />
                    <AvatarFallback>
                      {user?.full_name?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase()}
                    </AvatarFallback>
                  </Avatar>

                  <span
                    className="text-sm font-medium truncate max-w-[130px]"
                    title={user?.full_name || user?.email}
                  >
                    {user?.full_name || user?.email}
                  </span>

                  <ChevronDown
                    className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`}
                  />
                </button>
              </DropdownMenuTrigger>

              <DropdownMenuContent align="end" className="w-40 p-1 shadow-lg border rounded-md">
                <DropdownMenuItem
                  onClick={async () => {
                    setOpen(false);
                    await logout();
                  }}
                  className="cursor-pointer"
                >
                  <LogOut className="h-4 w-4 mr-2" />
                  Log Out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    </header>
  );
};
