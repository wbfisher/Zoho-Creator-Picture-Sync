import { useEffect, useCallback, useState } from 'react'
import { useQuery, useInfiniteQuery } from '@tanstack/react-query'
import { RowsPhotoAlbum } from 'react-photo-album'
import 'react-photo-album/rows.css'
import { getImages, getFilterValues } from '@/lib/api'
import { useGalleryStore } from '@/store'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/hooks/use-toast'
import { formatBytes, debounce } from '@/lib/utils'
import { Lightbox } from '@/components/Lightbox'
import type { Image as ImageType } from '@/types'
import {
  Search,
  X,
  Download,
  Loader2,
  CheckSquare,
  Square,
  Image as ImageIcon,
  AlertCircle,
} from 'lucide-react'
import JSZip from 'jszip'

const ITEMS_PER_PAGE = 50

export default function Gallery() {
  const { toast } = useToast()
  const [imageErrors, setImageErrors] = useState<Set<string>>(new Set())

  const {
    selectedImages,
    toggleSelection,
    selectAll,
    clearSelection,
    filters,
    setFilter,
    resetFilters,
    openLightbox,
    setGalleryImages,
  } = useGalleryStore()

  // Fetch filter options
  const { data: filterValues } = useQuery({
    queryKey: ['filterValues'],
    queryFn: getFilterValues,
  })

  // Infinite query for images
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
    error,
  } = useInfiniteQuery({
    queryKey: ['images', filters],
    queryFn: ({ pageParam = 0 }) => getImages(filters, ITEMS_PER_PAGE, pageParam),
    getNextPageParam: (lastPage, allPages) => {
      const totalFetched = allPages.reduce((sum, page) => sum + page.items.length, 0)
      return totalFetched < lastPage.total ? totalFetched : undefined
    },
    initialPageParam: 0,
  })

  // Flatten all pages into single array
  const allImages = data?.pages.flatMap((page) => page.items) ?? []
  const totalImages = data?.pages[0]?.total ?? 0

  // Update gallery store for lightbox navigation
  useEffect(() => {
    setGalleryImages(allImages)
  }, [allImages, setGalleryImages])

  // Extended photo type to include our custom data
  type ExtendedPhoto = {
    src: string
    width: number
    height: number
    key: string
    alt: string
    image: ImageType
    originalIndex: number
  }

  // Convert images to photo album format
  const photos: ExtendedPhoto[] = allImages.map((image, index) => ({
    src: image.url || '',
    width: 800,
    height: 600,
    key: image.id,
    alt: image.original_filename,
    image,
    originalIndex: index,
  }))

  // Debounced search
  const debouncedSearch = useCallback(
    debounce((value: string) => setFilter('search', value || undefined), 300),
    [setFilter]
  )

  // Bulk download
  const handleBulkDownload = async () => {
    if (selectedImages.size === 0) return

    toast({ title: 'Preparing download...', description: `${selectedImages.size} images` })

    try {
      const zip = new JSZip()
      const imageIds = Array.from(selectedImages)

      for (const id of imageIds) {
        const image = allImages.find((img) => img.id === id)
        if (!image?.url) continue

        const response = await fetch(image.url)
        const blob = await response.blob()
        const filename = image.original_filename || `${id}.webp`
        zip.file(filename, blob)
      }

      const zipBlob = await zip.generateAsync({ type: 'blob' })
      const url = URL.createObjectURL(zipBlob)
      const a = document.createElement('a')
      a.href = url
      a.download = `zoho-pictures-${new Date().toISOString().split('T')[0]}.zip`
      a.click()
      URL.revokeObjectURL(url)

      toast({ title: 'Download complete', description: `${selectedImages.size} images downloaded` })
      clearSelection()
    } catch (err) {
      toast({ title: 'Download failed', description: String(err), variant: 'destructive' })
    }
  }

  const handleSelectAll = () => {
    if (selectedImages.size === allImages.length) {
      clearSelection()
    } else {
      selectAll(allImages.map((img) => img.id))
    }
  }

  const handleImageError = (imageId: string) => {
    setImageErrors((prev) => new Set(prev).add(imageId))
  }

  const activeFiltersCount = Object.values(filters).filter(Boolean).length

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search images..."
            className="pl-9"
            onChange={(e) => debouncedSearch(e.target.value)}
          />
        </div>

        {/* Filters */}
        <Select
          value={filters.job_captain_timesheet || ''}
          onValueChange={(val) => setFilter('job_captain_timesheet', val || undefined)}
        >
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Job Captain Timesheet" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All Timesheets</SelectItem>
            {filterValues?.job_captain_timesheets.map((jc) => (
              <SelectItem key={jc} value={jc}>{jc}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.project_name || ''}
          onValueChange={(val) => setFilter('project_name', val || undefined)}
        >
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Project" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All Projects</SelectItem>
            {filterValues?.project_names.map((proj) => (
              <SelectItem key={proj} value={proj}>{proj}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.department || ''}
          onValueChange={(val) => setFilter('department', val || undefined)}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Department" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All Departments</SelectItem>
            {filterValues?.departments.map((dept) => (
              <SelectItem key={dept} value={dept}>{dept}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {activeFiltersCount > 0 && (
          <Button variant="ghost" size="sm" onClick={resetFilters}>
            <X className="mr-1 h-4 w-4" />
            Clear ({activeFiltersCount})
          </Button>
        )}
      </div>

      {/* Selection toolbar */}
      <div className="flex items-center justify-between border-b pb-3">
        <div className="flex items-center gap-4">
          <Button variant="outline" size="sm" onClick={handleSelectAll}>
            {selectedImages.size === allImages.length && allImages.length > 0 ? (
              <CheckSquare className="mr-2 h-4 w-4" />
            ) : (
              <Square className="mr-2 h-4 w-4" />
            )}
            {selectedImages.size > 0 ? `${selectedImages.size} selected` : 'Select All'}
          </Button>

          {selectedImages.size > 0 && (
            <>
              <Button variant="outline" size="sm" onClick={handleBulkDownload}>
                <Download className="mr-2 h-4 w-4" />
                Download ZIP
              </Button>
              <Button variant="ghost" size="sm" onClick={clearSelection}>
                Clear Selection
              </Button>
            </>
          )}
        </div>

        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <ImageIcon className="h-4 w-4" />
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <span>
              {allImages.length.toLocaleString()} of {totalImages.toLocaleString()} images
            </span>
          )}
        </div>
      </div>

      {/* Gallery Grid */}
      <div className="flex-1 overflow-auto rounded-lg border bg-muted/30 p-4">
        {isLoading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : isError ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
            <AlertCircle className="h-12 w-12" />
            <p>Failed to load images</p>
            <p className="text-sm">{error?.message}</p>
          </div>
        ) : allImages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
            <ImageIcon className="h-12 w-12" />
            <p>No images found</p>
            {activeFiltersCount > 0 && (
              <Button variant="link" size="sm" onClick={resetFilters}>
                Clear filters
              </Button>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <RowsPhotoAlbum
              photos={photos}
              targetRowHeight={180}
              rowConstraints={{ minPhotos: 3, maxPhotos: 6 }}
              spacing={8}
              render={{
                photo: (_props, { photo, width, height }) => {
                  const extPhoto = photo as ExtendedPhoto
                  const { image, originalIndex } = extPhoto
                  const isSelected = selectedImages.has(image.id)
                  const hasError = imageErrors.has(image.id)

                  return (
                    <div
                      key={image.id}
                      className={`group relative overflow-hidden rounded-md bg-background transition-all cursor-pointer ${
                        isSelected ? 'ring-2 ring-primary ring-offset-2' : ''
                      }`}
                      style={{ width, height }}
                    >
                      {hasError || !image.url ? (
                        <div className="flex h-full w-full items-center justify-center bg-muted">
                          <ImageIcon className="h-8 w-8 text-muted-foreground" />
                        </div>
                      ) : (
                        <img
                          src={image.url}
                          alt={image.original_filename}
                          loading="lazy"
                          className="h-full w-full object-cover transition-transform group-hover:scale-105"
                          onClick={() => openLightbox(image, originalIndex)}
                          onError={() => handleImageError(image.id)}
                        />
                      )}

                      {/* Checkbox overlay */}
                      <div
                        className={`absolute left-2 top-2 transition-opacity ${
                          isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                        }`}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Checkbox
                          checked={isSelected}
                          onCheckedChange={() => toggleSelection(image.id)}
                          className="h-5 w-5 border-2 border-white bg-black/50 data-[state=checked]:bg-primary"
                        />
                      </div>

                      {/* Info overlay */}
                      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-2 opacity-0 transition-opacity group-hover:opacity-100">
                        <p className="truncate text-xs font-medium text-white">
                          {image.original_filename}
                        </p>
                        <div className="flex items-center gap-1 text-xs text-white/70">
                          <span>{formatBytes(image.file_size_bytes)}</span>
                          {image.was_processed && (
                            <Badge variant="secondary" className="h-4 px-1 text-[10px]">
                              WebP
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                },
              }}
            />

            {/* Load more button */}
            {hasNextPage && (
              <div className="flex justify-center pt-4">
                <Button
                  variant="outline"
                  onClick={() => fetchNextPage()}
                  disabled={isFetchingNextPage}
                >
                  {isFetchingNextPage ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Loading...
                    </>
                  ) : (
                    <>Load more images</>
                  )}
                </Button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Lightbox */}
      <Lightbox />
    </div>
  )
}
