import { useEffect, useCallback, useRef, useMemo } from 'react'
import { useQuery, useInfiniteQuery } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
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
import type { Image } from '@/types'
import {
  Search,
  X,
  Download,
  Loader2,
  CheckSquare,
  Square,
  Image as ImageIcon,
} from 'lucide-react'
import JSZip from 'jszip'

const ITEMS_PER_PAGE = 100
const COLUMNS = 6
const ROW_HEIGHT = 180

export default function Gallery() {
  const { toast } = useToast()
  const parentRef = useRef<HTMLDivElement>(null)

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
  } = useInfiniteQuery({
    queryKey: ['images', filters],
    queryFn: ({ pageParam = 0 }) => getImages(filters, ITEMS_PER_PAGE, pageParam),
    getNextPageParam: (lastPage, allPages) => {
      const totalFetched = allPages.reduce((sum, page) => sum + page.items.length, 0)
      return totalFetched < lastPage.total ? totalFetched : undefined
    },
    initialPageParam: 0,
  })

  // Flatten all pages into single array (memoized to prevent infinite re-renders)
  const allImages = useMemo(
    () => data?.pages.flatMap((page) => page.items) ?? [],
    [data?.pages]
  )
  const totalImages = data?.pages[0]?.total ?? 0

  // Update gallery store for lightbox navigation
  useEffect(() => {
    setGalleryImages(allImages)
  }, [allImages, setGalleryImages])

  // Calculate rows for virtualization
  const rows = Math.ceil(allImages.length / COLUMNS)

  const rowVirtualizer = useVirtualizer({
    count: rows + (hasNextPage ? 1 : 0), // +1 for loading row
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 5,
  })

  // Get virtual items for rendering
  const virtualItems = rowVirtualizer.getVirtualItems()

  // Load more when approaching end
  useEffect(() => {
    const lastItem = virtualItems[virtualItems.length - 1]
    if (!lastItem) return

    if (
      lastItem.index >= rows - 1 &&
      hasNextPage &&
      !isFetchingNextPage
    ) {
      fetchNextPage()
    }
  }, [virtualItems.length, hasNextPage, isFetchingNextPage, fetchNextPage, rows])

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

      // Fetch each selected image
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
    } catch (error) {
      toast({ title: 'Download failed', description: String(error), variant: 'destructive' })
    }
  }

  const handleSelectAll = () => {
    if (selectedImages.size === allImages.length) {
      clearSelection()
    } else {
      selectAll(allImages.map((img) => img.id))
    }
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
          value={filters.job_captain_timesheet || '__all__'}
          onValueChange={(val) => setFilter('job_captain_timesheet', val === '__all__' ? undefined : val)}
        >
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Job Captain Timesheet" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Timesheets</SelectItem>
            {filterValues?.job_captain_timesheets.map((jc) => (
              <SelectItem key={jc} value={jc}>{jc}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.project_name || '__all__'}
          onValueChange={(val) => setFilter('project_name', val === '__all__' ? undefined : val)}
        >
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Project" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Projects</SelectItem>
            {filterValues?.project_names.map((proj) => (
              <SelectItem key={proj} value={proj}>{proj}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.department || '__all__'}
          onValueChange={(val) => setFilter('department', val === '__all__' ? undefined : val)}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Department" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Departments</SelectItem>
            {filterValues?.departments.map((dept) => (
              <SelectItem key={dept} value={dept}>{dept}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.photo_origin || '__all__'}
          onValueChange={(val) => setFilter('photo_origin', val === '__all__' ? undefined : val)}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Photo Origin" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Origins</SelectItem>
            {filterValues?.photo_origins?.map((origin) => (
              <SelectItem key={origin} value={origin}>{origin}</SelectItem>
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
            <span>{totalImages.toLocaleString()} images</span>
          )}
        </div>
      </div>

      {/* Virtualized Grid */}
      <div
        ref={parentRef}
        className="flex-1 overflow-auto rounded-lg border bg-muted/30"
      >
        {isLoading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : isError ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            Failed to load images
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
          <div
            style={{
              height: `${rowVirtualizer.getTotalSize()}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {virtualItems.map((virtualRow) => {
              const startIndex = virtualRow.index * COLUMNS
              const rowImages = allImages.slice(startIndex, startIndex + COLUMNS)

              // Loading indicator row
              if (virtualRow.index >= rows) {
                return (
                  <div
                    key="loading"
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                    className="flex items-center justify-center"
                  >
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                )
              }

              return (
                <div
                  key={virtualRow.index}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: `${virtualRow.size}px`,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                  className="grid grid-cols-6 gap-2 p-2"
                >
                  {rowImages.map((image, colIndex) => (
                    <ImageCard
                      key={image.id}
                      image={image}
                      index={startIndex + colIndex}
                      isSelected={selectedImages.has(image.id)}
                      onSelect={() => toggleSelection(image.id)}
                      onOpen={() => openLightbox(image, startIndex + colIndex)}
                    />
                  ))}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Lightbox */}
      <Lightbox />
    </div>
  )
}

interface ImageCardProps {
  image: Image
  index: number
  isSelected: boolean
  onSelect: () => void
  onOpen: () => void
}

function ImageCard({ image, isSelected, onSelect, onOpen }: ImageCardProps) {
  return (
    <div
      className={`group relative aspect-square overflow-hidden rounded-md bg-background transition-all ${
        isSelected ? 'ring-2 ring-primary ring-offset-2' : ''
      }`}
    >
      <img
        src={image.url}
        alt={image.original_filename}
        loading="lazy"
        className="h-full w-full cursor-pointer object-cover transition-transform group-hover:scale-105"
        onClick={onOpen}
      />

      {/* Checkbox overlay */}
      <div
        className={`absolute left-2 top-2 transition-opacity ${
          isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
        }`}
      >
        <Checkbox
          checked={isSelected}
          onCheckedChange={onSelect}
          className="h-5 w-5 border-2 border-white bg-black/50 data-[state=checked]:bg-primary"
        />
      </div>

      {/* Info overlay */}
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-2 opacity-0 transition-opacity group-hover:opacity-100">
        <p className="truncate text-xs font-medium text-white">{image.original_filename}</p>
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
}
