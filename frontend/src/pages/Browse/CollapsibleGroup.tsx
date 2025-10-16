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
            className="rounded-lg shadow-sm p-4 cursor-pointer flex items-center justify-between mb-2 transition-shadow border border-gray-300"
            onClick={() => setOpen((prev) => !prev)}
            whileTap={{ scale: 0.98 }}
          >
            <div className="flex-1 flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold text-lg text-gray-800">{title}</h2>
                <motion.span
                  animate={{ rotate: open ? 90 : 0 }}
                  transition={{ type: 'spring', stiffness: 200, damping: 30 }}
                  className="inline-block ml-2"
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
                  className="text-sm text-gray-500 px-1"
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
                className="pl-4 pt-4 pb-2 flex flex-col gap-4"
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
