"""
File operations service for freeMarkable.

This module provides file download with progress tracking, archive extraction,
temporary file management and cleanup, and path utilities.
"""

import os
import shutil
import tempfile
import zipfile
import hashlib
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, Union, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
import time
from dataclasses import dataclass
from enum import Enum


class DownloadStatus(Enum):
    """Download status states."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExtractionStatus(Enum):
    """Archive extraction status states."""
    PENDING = "pending"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DownloadProgress:
    """Progress information for downloads."""
    url: str
    filename: str
    total_size: Optional[int] = None
    downloaded_size: int = 0
    status: DownloadStatus = DownloadStatus.PENDING
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error_message: Optional[str] = None
    
    @property
    def progress_percentage(self) -> float:
        """Get download progress as percentage."""
        if self.total_size and self.total_size > 0:
            return (self.downloaded_size / self.total_size) * 100.0
        return 0.0
    
    @property
    def download_speed(self) -> Optional[float]:
        """Get download speed in bytes per second."""
        if self.start_time and self.downloaded_size > 0:
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                return self.downloaded_size / elapsed
        return None
    
    @property
    def eta_seconds(self) -> Optional[float]:
        """Get estimated time to completion in seconds."""
        if self.total_size and self.download_speed and self.download_speed > 0:
            remaining_bytes = self.total_size - self.downloaded_size
            return remaining_bytes / self.download_speed
        return None


@dataclass
class FileItem:
    """Information about a downloaded/managed file."""
    name: str
    path: Path
    url: Optional[str] = None
    size: Optional[int] = None
    checksum: Optional[str] = None
    is_archive: bool = False
    extraction_path: Optional[Path] = None
    
    def calculate_checksum(self, algorithm: str = "sha256") -> str:
        """Calculate file checksum."""
        hash_obj = hashlib.new(algorithm)
        with open(self.path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_obj.update(chunk)
        self.checksum = hash_obj.hexdigest()
        return self.checksum


class FileService:
    """
    File operations service for managing downloads, extractions, and cleanup.
    
    Provides comprehensive file management including downloading with progress tracking,
    archive extraction, temporary file management, and path utilities.
    """
    
    def __init__(self, downloads_dir: Optional[Path] = None,
                 temp_dir: Optional[Path] = None,
                 chunk_size: int = 8192,
                 timeout: int = 300,
                 max_retries: int = 3):
        """
        Initialize file service.
        
        Args:
            downloads_dir: Directory for downloaded files (default: ./downloads)
            temp_dir: Directory for temporary files (default: system temp)
            chunk_size: Download chunk size in bytes
            timeout: Download timeout in seconds
            max_retries: Maximum download retry attempts
        """
        self.downloads_dir = downloads_dir or Path("downloads")
        self.temp_dir = temp_dir
        self.chunk_size = chunk_size
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Ensure downloads directory exists
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        
        # Progress tracking
        self.progress_callback: Optional[Callable[[DownloadProgress], None]] = None
        
        # File management
        self.managed_files: Dict[str, FileItem] = {}
        self.temp_files: List[Path] = []
        self.temp_dirs: List[Path] = []
        
        self._logger = logging.getLogger(__name__)
    
    def set_progress_callback(self, callback: Callable[[DownloadProgress], None]) -> None:
        """
        Set progress callback function.
        
        Args:
            callback: Function called with DownloadProgress for each update
        """
        self.progress_callback = callback
    
    def download_file(self, url: str, filename: Optional[str] = None,
                     destination: Optional[Path] = None,
                     expected_checksum: Optional[str] = None,
                     checksum_algorithm: str = "sha256") -> FileItem:
        """
        Download a file with progress tracking and validation.
        
        Args:
            url: URL to download from
            filename: Optional filename override
            destination: Optional destination directory
            expected_checksum: Optional checksum for validation
            checksum_algorithm: Algorithm for checksum calculation
            
        Returns:
            FileItem with download information
            
        Raises:
            URLError: If download fails
            ValueError: If checksum validation fails
        """
        # Determine filename and destination
        if not filename:
            parsed_url = urlparse(url)
            filename = Path(parsed_url.path).name or "download"
        
        if not destination:
            destination = self.downloads_dir
        
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        
        file_path = destination / filename
        
        # Create progress tracker
        progress = DownloadProgress(url=url, filename=filename)
        
        self._logger.info(f"Downloading {url} to {file_path}")
        
        # Attempt download with retries
        last_error = None
        for attempt in range(self.max_retries):
            try:
                progress.status = DownloadStatus.DOWNLOADING
                progress.start_time = time.time()
                self._update_progress(progress)
                
                # Create request with headers
                request = Request(url)
                request.add_header('User-Agent', 'freeMarkable/1.0')
                
                with urlopen(request, timeout=self.timeout) as response:
                    # Get content length if available
                    content_length = response.headers.get('Content-Length')
                    if content_length:
                        progress.total_size = int(content_length)
                    
                    # Download with progress tracking
                    with open(file_path, 'wb') as f:
                        while True:
                            chunk = response.read(self.chunk_size)
                            if not chunk:
                                break
                            
                            f.write(chunk)
                            progress.downloaded_size += len(chunk)
                            self._update_progress(progress)
                
                progress.status = DownloadStatus.COMPLETED
                progress.end_time = time.time()
                self._update_progress(progress)
                
                break  # Success, exit retry loop
                
            except (URLError, HTTPError, OSError) as e:
                last_error = e
                progress.status = DownloadStatus.FAILED
                progress.error_message = str(e)
                
                self._logger.warning(f"Download attempt {attempt + 1} failed: {e}")
                
                if attempt < self.max_retries - 1:
                    self._logger.info(f"Retrying download in 2 seconds...")
                    time.sleep(2)
                else:
                    self._update_progress(progress)
                    raise URLError(f"Download failed after {self.max_retries} attempts: {last_error}")
        
        # Create file item
        file_item = FileItem(
            name=filename,
            path=file_path,
            url=url,
            size=file_path.stat().st_size,
            is_archive=filename.lower().endswith(('.zip', '.tar', '.tar.gz', '.tgz'))
        )
        
        # Validate checksum if provided
        if expected_checksum:
            calculated_checksum = file_item.calculate_checksum(checksum_algorithm)
            if calculated_checksum.lower() != expected_checksum.lower():
                file_path.unlink()  # Remove invalid file
                raise ValueError(f"Checksum validation failed. Expected: {expected_checksum}, Got: {calculated_checksum}")
            
            self._logger.info(f"Checksum validation successful: {calculated_checksum}")
        
        # Store managed file
        self.managed_files[filename] = file_item
        
        self._logger.info(f"Download completed: {filename} ({file_item.size} bytes)")
        return file_item
    
    def _update_progress(self, progress: DownloadProgress) -> None:
        """Update progress callback if set."""
        if self.progress_callback:
            try:
                self.progress_callback(progress)
            except Exception as e:
                self._logger.warning(f"Progress callback error: {e}")
    
    def extract_archive(self, archive_path: Union[str, Path],
                       destination: Optional[Path] = None,
                       progress_callback: Optional[Callable[[str, int, int], None]] = None) -> Path:
        """
        Extract archive file with progress tracking.
        
        Args:
            archive_path: Path to archive file
            destination: Extraction destination (default: same directory as archive)
            progress_callback: Optional callback for extraction progress (filename, current, total)
            
        Returns:
            Path to extraction directory
            
        Raises:
            ValueError: If archive format is not supported
            zipfile.BadZipFile: If zip file is corrupted
        """
        archive_path = Path(archive_path)
        
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")
        
        if not destination:
            destination = archive_path.parent
        
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        
        # Determine extraction directory name
        extract_dir = destination / archive_path.stem
        
        self._logger.info(f"Extracting {archive_path} to {extract_dir}")
        
        if archive_path.suffix.lower() == '.zip':
            return self._extract_zip(archive_path, extract_dir, progress_callback)
        else:
            raise ValueError(f"Unsupported archive format: {archive_path.suffix}")
    
    def _extract_zip(self, zip_path: Path, destination: Path,
                    progress_callback: Optional[Callable[[str, int, int], None]] = None) -> Path:
        """Extract ZIP archive with progress tracking."""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                members = zip_ref.infolist()
                total_files = len(members)
                
                # Remove existing extraction directory if it exists
                if destination.exists():
                    shutil.rmtree(destination)
                
                destination.mkdir(parents=True, exist_ok=True)
                
                for i, member in enumerate(members):
                    try:
                        # Update progress
                        if progress_callback:
                            progress_callback(member.filename, i + 1, total_files)
                        
                        # Extract member
                        zip_ref.extract(member, destination)
                        
                        # Fix permissions for extracted files
                        extracted_path = destination / member.filename
                        if extracted_path.exists() and not extracted_path.is_dir():
                            # Make scripts executable
                            if extracted_path.suffix in ['.sh', ''] and not extracted_path.is_dir():
                                extracted_path.chmod(0o755)
                    
                    except Exception as e:
                        self._logger.warning(f"Failed to extract {member.filename}: {e}")
                        continue
                
                self._logger.info(f"Extracted {total_files} files to {destination}")
                return destination
                
        except zipfile.BadZipFile as e:
            raise zipfile.BadZipFile(f"Corrupted ZIP file: {zip_path}") from e
    
    def create_temp_file(self, suffix: str = "", prefix: str = "xovi_",
                        content: Optional[Union[str, bytes]] = None) -> Path:
        """
        Create a temporary file.
        
        Args:
            suffix: File suffix/extension
            prefix: File prefix
            content: Optional initial content
            
        Returns:
            Path to temporary file
        """
        if self.temp_dir:
            temp_dir = self.temp_dir
        else:
            temp_dir = Path(tempfile.gettempdir())
        
        # Create temporary file
        fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=temp_dir)
        temp_path = Path(temp_path)
        
        try:
            if content is not None:
                if isinstance(content, str):
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        f.write(content)
                else:
                    with os.fdopen(fd, 'wb') as f:
                        f.write(content)
            else:
                os.close(fd)
        except Exception:
            os.close(fd)
            if temp_path.exists():
                temp_path.unlink()
            raise
        
        # Track temporary file
        self.temp_files.append(temp_path)
        self._logger.debug(f"Created temporary file: {temp_path}")
        
        return temp_path
    
    def create_temp_dir(self, suffix: str = "", prefix: str = "xovi_") -> Path:
        """
        Create a temporary directory.
        
        Args:
            suffix: Directory suffix
            prefix: Directory prefix
            
        Returns:
            Path to temporary directory
        """
        if self.temp_dir:
            temp_dir = self.temp_dir
        else:
            temp_dir = Path(tempfile.gettempdir())
        
        temp_path = Path(tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=temp_dir))
        
        # Track temporary directory
        self.temp_dirs.append(temp_path)
        self._logger.debug(f"Created temporary directory: {temp_path}")
        
        return temp_path
    
    def copy_file(self, source: Union[str, Path], destination: Union[str, Path],
                 create_dirs: bool = True) -> Path:
        """
        Copy file with directory creation.
        
        Args:
            source: Source file path
            destination: Destination file path
            create_dirs: Whether to create destination directories
            
        Returns:
            Path to copied file
        """
        source = Path(source)
        destination = Path(destination)
        
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")
        
        if create_dirs:
            destination.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(source, destination)
        self._logger.debug(f"Copied {source} to {destination}")
        
        return destination
    
    def ensure_directory(self, directory: Union[str, Path]) -> Path:
        """
        Ensure directory exists, creating it if necessary.
        
        Args:
            directory: Directory path
            
        Returns:
            Path to directory
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    
    def get_file_info(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Get comprehensive file information.
        
        Args:
            file_path: Path to file
            
        Returns:
            Dictionary with file information
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            return {"exists": False, "path": str(file_path)}
        
        stat = file_path.stat()
        
        info = {
            "exists": True,
            "path": str(file_path),
            "name": file_path.name,
            "size": stat.st_size,
            "is_file": file_path.is_file(),
            "is_dir": file_path.is_dir(),
            "is_symlink": file_path.is_symlink(),
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "accessed": stat.st_atime,
            "permissions": oct(stat.st_mode)[-3:]
        }
        
        if file_path.is_file():
            info["extension"] = file_path.suffix
            info["is_archive"] = file_path.suffix.lower() in ['.zip', '.tar', '.tar.gz', '.tgz']
        
        return info
    
    def cleanup_temp_files(self) -> int:
        """
        Clean up all tracked temporary files and directories.
        
        Returns:
            Number of items cleaned up
        """
        cleaned_count = 0
        
        # Clean up temporary files
        for temp_file in self.temp_files[:]:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    self._logger.debug(f"Cleaned up temporary file: {temp_file}")
                self.temp_files.remove(temp_file)
                cleaned_count += 1
            except Exception as e:
                self._logger.warning(f"Failed to clean up temporary file {temp_file}: {e}")
        
        # Clean up temporary directories
        for temp_dir in self.temp_dirs[:]:
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                    self._logger.debug(f"Cleaned up temporary directory: {temp_dir}")
                self.temp_dirs.remove(temp_dir)
                cleaned_count += 1
            except Exception as e:
                self._logger.warning(f"Failed to clean up temporary directory {temp_dir}: {e}")
        
        if cleaned_count > 0:
            self._logger.info(f"Cleaned up {cleaned_count} temporary items")
        
        return cleaned_count
    
    def cleanup_downloads(self, keep_archives: bool = False) -> int:
        """
        Clean up downloaded files.
        
        Args:
            keep_archives: Whether to keep archive files
            
        Returns:
            Number of files cleaned up
        """
        cleaned_count = 0
        
        for filename, file_item in list(self.managed_files.items()):
            try:
                # Skip archives if requested
                if keep_archives and file_item.is_archive:
                    continue
                
                if file_item.path.exists():
                    file_item.path.unlink()
                    self._logger.debug(f"Cleaned up downloaded file: {file_item.path}")
                
                # Clean up extraction directory if it exists
                if file_item.extraction_path and file_item.extraction_path.exists():
                    shutil.rmtree(file_item.extraction_path)
                    self._logger.debug(f"Cleaned up extraction directory: {file_item.extraction_path}")
                
                del self.managed_files[filename]
                cleaned_count += 1
                
            except Exception as e:
                self._logger.warning(f"Failed to clean up {filename}: {e}")
        
        if cleaned_count > 0:
            self._logger.info(f"Cleaned up {cleaned_count} downloaded files")
        
        return cleaned_count
    
    def get_managed_files(self) -> Dict[str, FileItem]:
        """Get dictionary of all managed files."""
        return self.managed_files.copy()
    
    def get_download_progress(self) -> Dict[str, Any]:
        """Get overall download progress information."""
        total_files = len(self.managed_files)
        total_size = sum(f.size or 0 for f in self.managed_files.values())
        
        return {
            "total_files": total_files,
            "total_size": total_size,
            "downloads_dir": str(self.downloads_dir),
            "temp_files_count": len(self.temp_files),
            "temp_dirs_count": len(self.temp_dirs)
        }
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup_temp_files()


# Global file service instance
_global_file_service: Optional[FileService] = None


def get_file_service() -> FileService:
    """
    Get the global file service instance.
    
    Returns:
        Global FileService instance
        
    Raises:
        RuntimeError: If file service hasn't been initialized
    """
    global _global_file_service
    if _global_file_service is None:
        raise RuntimeError("File service not initialized. Call init_file_service() first.")
    return _global_file_service


def init_file_service(downloads_dir: Optional[Path] = None,
                     **kwargs) -> FileService:
    """
    Initialize the global file service.
    
    Args:
        downloads_dir: Downloads directory path
        **kwargs: Additional FileService initialization arguments
        
    Returns:
        Initialized FileService instance
    """
    global _global_file_service
    
    _global_file_service = FileService(downloads_dir=downloads_dir, **kwargs)
    return _global_file_service


def configure_from_config(config: Any) -> FileService:
    """
    Configure file service from application config.
    
    Args:
        config: Application configuration object
        
    Returns:
        Configured file service
    """
    downloads_dir = None
    if hasattr(config, 'get_downloads_directory'):
        downloads_dir = config.get_downloads_directory()
    elif hasattr(config, 'paths') and hasattr(config.paths, 'downloads_dir'):
        downloads_dir = Path(config.paths.downloads_dir)
    
    kwargs = {}
    if hasattr(config, 'downloads'):
        if hasattr(config.downloads, 'chunk_size'):
            kwargs['chunk_size'] = config.downloads.chunk_size
        if hasattr(config.downloads, 'download_timeout'):
            kwargs['timeout'] = config.downloads.download_timeout
        if hasattr(config.downloads, 'max_retries'):
            kwargs['max_retries'] = config.downloads.max_retries
    
    return init_file_service(downloads_dir=downloads_dir, **kwargs)


# Convenience functions

def download_file(url: str, filename: Optional[str] = None, **kwargs) -> FileItem:
    """Download a file (convenience function)."""
    return get_file_service().download_file(url, filename, **kwargs)


def extract_archive(archive_path: Union[str, Path], **kwargs) -> Path:
    """Extract an archive (convenience function)."""
    return get_file_service().extract_archive(archive_path, **kwargs)


def cleanup_temp_files() -> int:
    """Clean up temporary files (convenience function)."""
    return get_file_service().cleanup_temp_files()


def create_temp_file(**kwargs) -> Path:
    """Create a temporary file (convenience function)."""
    return get_file_service().create_temp_file(**kwargs)


def create_temp_dir(**kwargs) -> Path:
    """Create a temporary directory (convenience function)."""
    return get_file_service().create_temp_dir(**kwargs)


# Testing and utility functions

def test_file_service() -> None:
    """Test file service functionality."""
    print("Testing File Service:")
    print()
    
    # Initialize file service
    service = FileService(downloads_dir=Path("test_downloads"))
    
    print(f"Downloads directory: {service.downloads_dir}")
    print(f"Managed files: {len(service.managed_files)}")
    
    # Test temp file creation
    temp_file = service.create_temp_file(suffix=".txt", content="test content")
    print(f"Created temp file: {temp_file}")
    
    # Test temp directory creation
    temp_dir = service.create_temp_dir()
    print(f"Created temp directory: {temp_dir}")
    
    # Test file info
    info = service.get_file_info(temp_file)
    print(f"File info: size={info['size']}, exists={info['exists']}")
    
    # Test cleanup
    cleaned = service.cleanup_temp_files()
    print(f"Cleaned up {cleaned} temporary items")
    
    # Test download progress
    progress = service.get_download_progress()
    print(f"Download progress: {progress}")


if __name__ == "__main__":
    test_file_service()