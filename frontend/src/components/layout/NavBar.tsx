import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

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

        {/* Right: User Avatar Dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            className="flex items-center gap-2 focus:outline-none"
            onClick={() => setOpen((v) => !v)}
            aria-haspopup="true"
            aria-expanded={open}
          >
            <Avatar>
              <AvatarImage src="/avatars/jane.jpg" alt="Jane Doe" />
              <AvatarFallback>JD</AvatarFallback>
            </Avatar>
            <span className="text-sm font-medium">Jane Doe</span>
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
                onClick={() => {
                  setOpen(false);
                  // Placeholder: handle profile
                }}
              >
                View Profile
              </button>
              <button
                className="w-full text-left px-4 py-2 text-sm hover:bg-gray-100"
                onClick={() => {
                  setOpen(false);
                  // Placeholder: handle logout
                }}
              >
                Log Out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
