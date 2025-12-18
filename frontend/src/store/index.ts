import { create } from 'zustand'
import type { Image, FilterOptions } from '@/types'

// Re-export auth store
export { useAuthStore } from './auth'

interface GalleryState {
  // Selection
  selectedImages: Set<string>
  toggleSelection: (id: string) => void
  selectAll: (ids: string[]) => void
  clearSelection: () => void

  // Filters
  filters: FilterOptions
  setFilter: <K extends keyof FilterOptions>(key: K, value: FilterOptions[K]) => void
  resetFilters: () => void

  // Lightbox
  lightboxImage: Image | null
  lightboxIndex: number
  openLightbox: (image: Image, index: number) => void
  closeLightbox: () => void
  nextImage: () => void
  prevImage: () => void

  // Gallery data (for lightbox navigation)
  galleryImages: Image[]
  setGalleryImages: (images: Image[]) => void
}

const defaultFilters: FilterOptions = {
  job_captain_timesheet: undefined,
  project_name: undefined,
  department: undefined,
  photo_origin: undefined,
  search: undefined,
  date_from: undefined,
  date_to: undefined,
}

export const useGalleryStore = create<GalleryState>((set, get) => ({
  // Selection
  selectedImages: new Set(),
  toggleSelection: (id) =>
    set((state) => {
      const newSelected = new Set(state.selectedImages)
      if (newSelected.has(id)) {
        newSelected.delete(id)
      } else {
        newSelected.add(id)
      }
      return { selectedImages: newSelected }
    }),
  selectAll: (ids) =>
    set(() => ({ selectedImages: new Set(ids) })),
  clearSelection: () => set({ selectedImages: new Set() }),

  // Filters
  filters: defaultFilters,
  setFilter: (key, value) =>
    set((state) => ({
      filters: { ...state.filters, [key]: value || undefined },
    })),
  resetFilters: () => set({ filters: defaultFilters }),

  // Lightbox
  lightboxImage: null,
  lightboxIndex: 0,
  openLightbox: (image, index) => set({ lightboxImage: image, lightboxIndex: index }),
  closeLightbox: () => set({ lightboxImage: null }),
  nextImage: () => {
    const { galleryImages, lightboxIndex } = get()
    if (lightboxIndex < galleryImages.length - 1) {
      set({
        lightboxIndex: lightboxIndex + 1,
        lightboxImage: galleryImages[lightboxIndex + 1],
      })
    }
  },
  prevImage: () => {
    const { galleryImages, lightboxIndex } = get()
    if (lightboxIndex > 0) {
      set({
        lightboxIndex: lightboxIndex - 1,
        lightboxImage: galleryImages[lightboxIndex - 1],
      })
    }
  },

  // Gallery data
  galleryImages: [],
  setGalleryImages: (images) => set({ galleryImages: images }),
}))
