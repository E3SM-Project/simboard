import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { useAuth } from '@/auth/AuthContext';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
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

export default function Navbar({ selectedSimulationIds }: NavBarProps) {
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
    <header className="w-full px-6 py-4 bg-white border-b">
      <div className="mx-auto flex max-w-[1440px] items-center justify-between px-6 py-4">
        {/* Left: Logo + Nav Links */}
        <div className="flex items-center gap-6">
          {/* Logo */}
          <Link to="/" className="text-xl font-bold flex items-center gap-2">
            <span className="text-muted-foreground">🔬🌍</span>
            SimBoard
          </Link>

          {/* Nav Links */}
          <nav className="flex gap-2">
            {navItems.map((item) => {
              const isCompare = item.label === 'Compare';

              return (
                <div key={item.href} className="relative flex items-center group">
                  <TooltipProvider delayDuration={150}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        {isCompare ? (
                          <Link
                            to={item.href}
                            className={cn(
                              'text-sm font-medium text-muted-foreground hover:text-foreground transition-all border-b-2 border-transparent px-2 py-1 rounded flex items-center gap-1',
                              location.pathname === item.href &&
                                'text-foreground border-foreground font-semibold',
                            )}
                          >
                            {item.label}
                            {selectedSimulationIds.length > 0 && (
                              <span className="ml-1 inline-flex items-center justify-center px-1.5 py-0.5 text-xs font-semibold rounded-full bg-blue-100 text-blue-800 transition-opacity">
                                {selectedSimulationIds.length}
                              </span>
                            )}
                          </Link>
                        ) : (
                          <Link
                            to={item.href}
                            className={cn(
                              'text-sm font-medium text-muted-foreground hover:text-foreground transition-all border-b-2 border-transparent px-2 py-1 rounded',
                              location.pathname === item.href &&
                                'text-foreground border-foreground font-semibold',
                            )}
                          >
                            {item.label}
                          </Link>
                        )}
                      </TooltipTrigger>
                      <TooltipContent
                        side="bottom"
                        className="bg-gray-900 text-white px-3 py-2 rounded shadow-lg text-xs"
                      >
                        {item.description}
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
              );
            })}
          </nav>
        </div>

        {/* Right: Auth Controls */}
        <div className="relative" ref={dropdownRef}>
          {loading ? (
            <span className="text-sm text-muted-foreground">Loading...</span>
          ) : !isAuthenticated ? (
            <button
              onClick={loginWithGithub}
              className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              Login with GitHub
              <span className="ml-2 align-middle">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width={18}
                  height={18}
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="inline-block"
                  aria-hidden="true"
                >
                  <path d="M12 2C6.477 2 2 6.484 2 12.021c0 4.428 2.865 8.184 6.839 9.504.5.092.682-.217.682-.483 0-.237-.009-.868-.014-1.703-2.782.605-3.369-1.342-3.369-1.342-.454-1.154-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.004.07 1.532 1.032 1.532 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.339-2.221-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.025A9.564 9.564 0 0 1 12 6.844c.85.004 1.705.115 2.504.337 1.909-1.295 2.748-1.025 2.748-1.025.546 1.378.202 2.397.1 2.65.64.7 1.028 1.595 1.028 2.688 0 3.847-2.337 4.695-4.566 4.944.359.309.678.919.678 1.852 0 1.336-.012 2.417-.012 2.747 0 .268.18.579.688.481C19.138 20.2 22 16.447 22 12.021 22 6.484 17.523 2 12 2z" />
                </svg>
              </span>
            </button>
          ) : (
            <>
              <button
                className="flex items-center gap-2 focus:outline-none"
                onClick={() => setOpen((v) => !v)}
                aria-haspopup="true"
                aria-expanded={open}
              >
                <Avatar>
                  <AvatarImage
                    src="/avatars/default.jpg"
                    alt={user?.full_name || user?.email || 'User'}
                  />
                  <AvatarFallback>
                    {user?.full_name
                      ?.split(' ')
                      .filter((n) => n.trim().length > 0)
                      .map((n) => n[0])
                      .join('') ||
                      user?.email?.[0]?.toUpperCase() ||
                      'U'}
                  </AvatarFallback>
                </Avatar>

                <span className="text-sm font-medium">{user?.full_name || user?.email}</span>

                <svg
                  className={`w-4 h-4 ml-1 transition-transform ${open ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 9l-7 7-7-7"
                  />
                </svg>
              </button>

              {open && (
                <div className="absolute right-0 mt-2 w-40 bg-white border rounded shadow-lg z-50">
                  <button
                    className="w-full text-left px-4 py-2 text-sm hover:bg-gray-100"
                    onClick={async () => {
                      setOpen(false);
                      await logout();
                    }}
                  >
                    Log Out
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </header>
  );
}
