"use client"

import { Check, ChevronDown } from "lucide-react"
import { Select as SelectPrimitive } from "radix-ui"
import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * Tema token'larıyla boyanan seçim kutusu (Radix Select). Yerel `<select>`'in açılır listesi işletim
 * sisteminin menüsüyle çizilir ve seçeneklere renk/simge verilemez; burada her seçenek kendi
 * içeriğini (ör. seviye rozeti) taşır. Klavye: ok tuşları, Enter, Esc, harfle arama.
 */
const Select = SelectPrimitive.Root
const SelectValue = SelectPrimitive.Value

function SelectTrigger({ className, children, ...props }: React.ComponentProps<typeof SelectPrimitive.Trigger>) {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      className={cn(
        "flex h-8 min-w-36 items-center justify-between gap-2 rounded-md border border-cizgi-guclu bg-kart px-2.5 text-sm text-metin",
        "transition-colors hover:border-metin-soluk hover:bg-kart-hover",
        "data-[state=open]:border-secim data-[state=open]:ring-1 data-[state=open]:ring-secim",
        "disabled:cursor-not-allowed disabled:opacity-50 data-[placeholder]:text-metin-soluk",
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDown aria-hidden className="size-4 shrink-0 text-metin-soluk" />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  )
}

function SelectContent({ className, children, ...props }: React.ComponentProps<typeof SelectPrimitive.Content>) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        data-slot="select-content"
        position="popper"
        sideOffset={4}
        className={cn(
          "z-50 max-h-(--radix-select-content-available-height) min-w-(--radix-select-trigger-width) overflow-hidden rounded-md border border-cizgi bg-kart text-metin shadow-golge-yuksek",
          "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          className,
        )}
        {...props}
      >
        <SelectPrimitive.Viewport className="p-1">{children}</SelectPrimitive.Viewport>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  )
}

function SelectItem({ className, children, ...props }: React.ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item
      data-slot="select-item"
      className={cn(
        "relative flex cursor-pointer items-center gap-2 rounded-sm py-1.5 pr-8 pl-2 text-sm outline-none select-none",
        "data-[highlighted]:bg-kart-hover data-[highlighted]:text-metin",
        "data-[state=checked]:bg-secim-zemin data-[state=checked]:font-bold",
        "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        className,
      )}
      {...props}
    >
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator className="absolute right-2 flex items-center">
        <Check aria-hidden className="size-4 text-secim" />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  )
}

function SelectSeparator({ className, ...props }: React.ComponentProps<typeof SelectPrimitive.Separator>) {
  return <SelectPrimitive.Separator className={cn("my-1 h-px bg-cizgi", className)} {...props} />
}

export { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue }
