import { ChevronRight } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useState } from 'react';

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';

interface GroupProps {
  title: string;
  description?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

const CollapsibleGroup = ({ title, description, children, defaultOpen = true }: GroupProps) => {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div>
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger asChild>
          <motion.div
            layout
            initial={false}
            className="mb-1 flex cursor-pointer items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2.5 transition-colors hover:bg-slate-50"
            onClick={() => setOpen((prev) => !prev)}
            whileTap={{ scale: 0.98 }}
          >
            <div className="flex flex-1 flex-col gap-1">
              <div className="flex items-center justify-between">
                <h2 className="text-[15px] font-semibold text-slate-900">{title}</h2>
                <motion.span
                  animate={{ rotate: open ? 90 : 0 }}
                  transition={{ type: 'spring', stiffness: 200, damping: 30 }}
                  className="ml-2 inline-block text-slate-500"
                >
                  <ChevronRight size={18} strokeWidth={2} />
                </motion.span>
              </div>
              {description && (
                <motion.p
                  key="desc"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
                  className="px-0.5 text-[11px] leading-4 text-slate-500"
                >
                  {description}
                </motion.p>
              )}
            </div>
          </motion.div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <AnimatePresence initial={false}>
            {open && (
              <motion.div
                key="content"
                initial={{ opacity: 0, y: -16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -16 }}
                transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
                className="flex flex-col gap-2.5 px-1 pb-1 pt-2"
              >
                {children}
              </motion.div>
            )}
          </AnimatePresence>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
};

export default CollapsibleGroup;
