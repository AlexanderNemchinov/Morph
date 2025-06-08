"""
Morph
Copyright (C) 2025 Alexander Nemchinov
https://linktr.ee/Nemchinov

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software Foundation,
Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""

import sys
import os
import subprocess
import time
import atexit
import configparser
import psutil
import webbrowser
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QStatusBar,
    QMenu,
    QListWidgetItem,
    QFileIconProvider,
    QTextEdit,
    QLabel,
)
from PyQt5.QtCore import Qt, QSize, QFileInfo, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QDragEnterEvent, QDropEvent, QPainter, QColor, QFont
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from PyQt5.QtWidgets import QStyle

try:
    from PyQt5.QtWinExtras import QWinTaskbarButton
    windows_taskbar_available = True
except ImportError:
    windows_taskbar_available = False

temp_files = set()
ffmpeg_processes = set()

def cleanup_temp_files(silent=True):
    for temp_file in list(temp_files):
        if os.path.exists(temp_file):
            for _ in range(5):
                try:
                    os.remove(temp_file)
                    temp_files.discard(temp_file)
                    break
                except Exception:
                    time.sleep(0.1)
    for temp_file in os.listdir('.'):
        if temp_file.startswith('temp_thumb_') and os.path.isfile(temp_file):
            for _ in range(5):
                try:
                    os.remove(temp_file)
                    break
                except Exception:
                    time.sleep(0.1)

def terminate_ffmpeg_processes():
    for pid in list(ffmpeg_processes):
        try:
            process = psutil.Process(pid)
            for child in process.children(recursive=True):
                try:
                    child.terminate()
                    child.wait(1)
                    if child.is_running():
                        child.kill()
                except psutil.NoSuchProcess:
                    pass
            process.terminate()
            process.wait(1)
            if process.is_running():
                process.kill()
            ffmpeg_processes.discard(pid)
        except psutil.NoSuchProcess:
            ffmpeg_processes.discard(pid)

atexit.register(cleanup_temp_files)
atexit.register(terminate_ffmpeg_processes)
cleanup_temp_files()

translations = {
    "ru": {
        "window_title": "Morph",
        "video": "Видео",
        "audio": "Аудио",
        "image": "Изображение",
        "clear_all": "Очистить все",
        "start": "Старт",
        "cancel": "Отмена",
        "clear": "Очистить",
        "converting": "Конвертация: {progress}%",
        "select_type_format": "Выберите тип и формат конвертации!",
        "collect_files_error": "Ошибка при сборе файлов: {error}",
        "no_valid_files": "Нет подходящих файлов",
        "file_access_error": "Ошибка доступа к файлу: {file}",
        "conversion_error": "Ошибка конвертации: {file}",
        "output_not_created": "Итоговый файл не создан: {file}",
        "completed_with_errors": "Завершено с ошибками: {failed} из {total} файлов не удалось конвертировать",
        "unexpected_error": "Неожиданная ошибка: {error}",
        "conversion_cancelled": "Конвертация отменена",
        "drag_drop": "ПЕРЕТАЩИТЕ ФАЙЛЫ\nСЮДА",
        "conversion_success": "Конвертация завершена успешно",
        "conversion_failed": "Конвертация не удалась: {failed} из {total} файлов не удалось конвертировать",
    },
    "en": {
        "window_title": "Morph",
        "video": "Video",
        "audio": "Audio",
        "image": "Image",
        "clear_all": "Clear All",
        "start": "Start",
        "cancel": "Cancel",
        "clear": "Clear",
        "converting": "Converting: {progress}%",
        "select_type_format": "Select type and format for conversion!",
        "collect_files_error": "Error collecting files: {error}",
        "no_valid_files": "No valid files found",
        "file_access_error": "Error accessing file: {file}",
        "conversion_error": "Error converting: {file}",
        "output_not_created": "Output file not created: {file}",
        "completed_with_errors": "Completed with errors: {failed} of {total} files failed to convert",
        "unexpected_error": "Unexpected error: {error}",
        "conversion_cancelled": "Conversion cancelled",
        "drag_drop": "DRAG &\nDROP",
        "conversion_success": "Conversion completed successfully",
        "conversion_failed": "Conversion failed: {failed} of {total} files failed to convert",
    }
}

def get_binary_path(binary_name):
    try:
        if getattr(sys, "frozen", False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_path, "bin", binary_name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Binary {binary_name} not found at {path}")
        return path
    except Exception as e:
        raise

ffmpeg_path = get_binary_path("ffmpeg.exe")
magick_path = get_binary_path("magick.exe")
exiftool_path = get_binary_path("exiftool.exe")
ffprobe_path = get_binary_path("ffprobe.exe")

video_extensions = [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts", ".mpeg", ".vob", ".m2ts", ".bdav", ".mpg"]
audio_extensions = [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".opus"]
image_extensions = [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp", ".jxr", ".heic", ".avif", ".ico", ".dng"]

def generate_thumbnail(file_path):
    if not os.path.exists(file_path):
        return None
    ext = os.path.splitext(file_path)[1].lower()
    temp_thumb = f"temp_thumb_{int(time.time()*1000)}_{os.path.basename(file_path)}.png"
    temp_files.add(temp_thumb)
    icon = None
    try:
        if ext in video_extensions:
            cmd = f'"{ffmpeg_path}" -i "{file_path}" -vf "thumbnail,scale=64:64" -frames:v 1 "{temp_thumb}" -y'
            process = subprocess.run(
                cmd, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if process.returncode == 0 and os.path.exists(temp_thumb):
                icon = QIcon(temp_thumb)
        elif ext in image_extensions:
            cmd = f'"{ffmpeg_path}" -i "{file_path}" -vf "scale=64:64" -frames:v 1 "{temp_thumb}" -y'
            process = subprocess.run(
                cmd, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if process.returncode == 0 and os.path.exists(temp_thumb):
                icon = QIcon(temp_thumb)
        elif ext in audio_extensions:
            cmd = f'"{ffmpeg_path}" -i "{file_path}" -an -vcodec copy "{temp_thumb}" -y'
            process = subprocess.run(
                cmd, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if process.returncode == 0 and os.path.exists(temp_thumb):
                icon = QIcon(temp_thumb)
    except subprocess.CalledProcessError:
        pass
    finally:
        if os.path.exists(temp_thumb):
            for _ in range(5):
                try:
                    os.remove(temp_thumb)
                    temp_files.discard(temp_thumb)
                    break
                except Exception:
                    time.sleep(0.1)
    return icon

def convert_video_to_mp4(input_path, output_path, progress_callback):
    cmd = f'"{ffmpeg_path}" -i "{input_path}" -map 0:v? -map 0:a? -map 0:s? -map 0:t? -map -0:d -c:v libx264 -crf 18 -preset slow -c:a copy -c:s copy -c:t copy -map_metadata 0 -fflags +genpts -progress pipe:1 "{output_path}"'
    try:
        process = subprocess.Popen(
            cmd, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8'
        )
        ffmpeg_processes.add(process.pid)
        duration = get_duration(input_path)
        while process.poll() is None:
            line = process.stdout.readline().strip()
            if line.startswith("out_time_ms="):
                try:
                    current_time = int(line.split("=")[1]) / 1000000
                    if duration > 0:
                        progress = min((current_time / duration) * 100, 100)
                        progress_callback(progress)
                except (ValueError, IndexError):
                    pass
            QApplication.processEvents()
        ffmpeg_processes.discard(process.pid)
        result = subprocess.CompletedProcess(args=cmd, returncode=process.returncode, stdout="", stderr="")
        return result
    except Exception as e:
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr=str(e))

def convert_video_to_mkv(input_path, output_path, progress_callback):
    cmd = f'"{ffmpeg_path}" -i "{input_path}" -map 0 -map -0:d -c:v copy -c:a copy -c:s copy -c:t copy -map_metadata 0 -fflags +genpts -progress pipe:1 "{output_path}"'
    try:
        process = subprocess.Popen(
            cmd, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8'
        )
        ffmpeg_processes.add(process.pid)
        duration = get_duration(input_path)
        while process.poll() is None:
            line = process.stdout.readline().strip()
            if line.startswith("out_time_ms="):
                try:
                    current_time = int(line.split("=")[1]) / 1000000
                    if duration > 0:
                        progress = min((current_time / duration) * 100, 100)
                        progress_callback(progress)
                except (ValueError, IndexError):
                    pass
            QApplication.processEvents()
        ffmpeg_processes.discard(process.pid)
        result = subprocess.CompletedProcess(args=cmd, returncode=process.returncode, stdout="", stderr="")
        return result
    except Exception as e:
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr=str(e))

def convert_video_to_webm(input_path, output_path, progress_callback):
    cmd = f'"{ffmpeg_path}" -i "{input_path}" -map 0:v? -map 0:a? -map 0:s? -c:v libvpx-vp9 -crf 18 -b:v 0 -deadline good -auto-alt-ref 0 -c:a libopus -b:a 320k -c:s copy -map_metadata 0 -fflags +genpts -threads 4 -progress pipe:1 "{output_path}"'
    try:
        process = subprocess.Popen(
            cmd, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8'
        )
        ffmpeg_processes.add(process.pid)
        duration = get_duration(input_path)
        while process.poll() is None:
            line = process.stdout.readline().strip()
            if line.startswith("out_time_ms="):
                try:
                    current_time = int(line.split("=")[1]) / 1000000
                    if duration > 0:
                        progress = min((current_time / duration) * 100, 100)
                        progress_callback(progress)
                except (ValueError, IndexError):
                    pass
            QApplication.processEvents()
        ffmpeg_processes.discard(process.pid)
        result = subprocess.CompletedProcess(args=cmd, returncode=process.returncode, stdout="", stderr="")
        return result
    except Exception as e:
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr=str(e))

def get_duration(input_path):
    cmd = f'"{ffprobe_path}" -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{input_path}"'
    try:
        process = subprocess.Popen(
            cmd, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        ffmpeg_processes.add(process.pid)
        output = process.communicate()[0].decode().strip()
        ffmpeg_processes.discard(process.pid)
        try:
            return float(output)
        except ValueError:
            return 0.0
    except (subprocess.CalledProcessError, ValueError):
        return 0.0

def get_audio_codec(input_path):
    cmd = f'"{ffprobe_path}" -v error -select_streams a:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "{input_path}"'
    try:
        process = subprocess.Popen(
            cmd, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        ffmpeg_processes.add(process.pid)
        output = process.communicate()[0].decode().strip()
        ffmpeg_processes.discard(process.pid)
        return output
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""

def convert_audio_to_m4a(input_path, output_path, progress_callback):
    codec = get_audio_codec(input_path)
    if codec in ["aac", "alac"]:
        cmd = f'"{ffmpeg_path}" -i "{input_path}" -map 0 -c copy -map_metadata 0 -progress pipe:1 "{output_path}"'
    else:
        cmd = f'"{ffmpeg_path}" -i "{input_path}" -map 0 -c:a alac -c:v copy -map_metadata 0 -progress pipe:1 "{output_path}"'
    try:
        process = subprocess.Popen(
            cmd, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8'
        )
        ffmpeg_processes.add(process.pid)
        duration = get_duration(input_path)
        while process.poll() is None:
            line = process.stdout.readline().strip()
            if line.startswith("out_time_ms="):
                try:
                    current_time = int(line.split("=")[1]) / 1000000
                    if duration > 0:
                        progress = min((current_time / duration) * 100, 100)
                        progress_callback(progress)
                except (ValueError, IndexError):
                    pass
            QApplication.processEvents()
        ffmpeg_processes.discard(process.pid)
        result = subprocess.CompletedProcess(args=cmd, returncode=process.returncode, stdout="", stderr="")
        return result
    except Exception as e:
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr=str(e))

def convert_audio_to_flac(input_path, output_path, progress_callback):
    codec = get_audio_codec(input_path)
    if codec == "flac":
        cmd = f'"{ffmpeg_path}" -i "{input_path}" -map 0 -c copy -map_metadata 0 -progress pipe:1 "{output_path}"'
    else:
        cmd = f'"{ffmpeg_path}" -i "{input_path}" -map 0 -c:a flac -c:v copy -map_metadata 0 -progress pipe:1 "{output_path}"'
    try:
        process = subprocess.Popen(
            cmd, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8'
        )
        ffmpeg_processes.add(process.pid)
        duration = get_duration(input_path)
        while process.poll() is None:
            line = process.stdout.readline().strip()
            if line.startswith("out_time_ms="):
                try:
                    current_time = int(line.split("=")[1]) / 1000000
                    if duration > 0:
                        progress = min((current_time / duration) * 100, 100)
                        progress_callback(progress)
                except (ValueError, IndexError):
                    pass
            QApplication.processEvents()
        ffmpeg_processes.discard(process.pid)
        result = subprocess.CompletedProcess(args=cmd, returncode=process.returncode, stdout="", stderr="")
        return result
    except Exception as e:
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr=str(e))

def convert_image_to_ico(input_path, output_path, progress_callback):
    cmd = f'"{ffmpeg_path}" -i "{input_path}" -vf scale=256:256 -frames:v 1 -map_metadata 0 "{output_path}"'
    try:
        process = subprocess.Popen(
            cmd, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8'
        )
        ffmpeg_processes.add(process.pid)
        while process.poll() is None:
            progress_callback(50)
            QApplication.processEvents()
        ffmpeg_processes.discard(process.pid)
        result = subprocess.CompletedProcess(args=cmd, returncode=process.returncode, stdout="", stderr="")
        return result
    except Exception as e:
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr=str(e))

def convert_image_to_jpg(input_path, output_path, progress_callback):
    try:
        density = subprocess.check_output(
            f'"{magick_path}" identify -format "%x" "{input_path}"',
            shell=True,
            creationflags=0x08000000
        ).decode().strip()
        cmd = f'"{magick_path}" "{input_path}" -strip -quality 95 -density {density} "{output_path}"'
        process = subprocess.Popen(
            cmd, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8'
        )
        while process.poll() is None:
            progress_callback(50)
            QApplication.processEvents()
        result = subprocess.CompletedProcess(args=cmd, returncode=process.returncode, stdout="", stderr="")
        return result
    except Exception as e:
        return subprocess.CompletedProcess(args=cmd if 'cmd' in locals() else "", returncode=1, stdout="", stderr=str(e))

def convert_image_to_png(input_path, output_path, progress_callback):
    cmd1 = f'"{ffmpeg_path}" -i "{input_path}" -c:v png -frames:v 1 -pix_fmt rgba "{output_path}"'
    try:
        process = subprocess.Popen(
            cmd1, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8'
        )
        ffmpeg_processes.add(process.pid)
        while process.poll() is None:
            progress_callback(50)
            QApplication.processEvents()
        ffmpeg_processes.discard(process.pid)
        result1 = subprocess.CompletedProcess(args=cmd1, returncode=process.returncode, stdout="", stderr="")
        if result1.returncode != 0:
            return result1
        cmd2 = f'"{exiftool_path}" -tagsfromfile "{input_path}" -all:all -XResolution -YResolution -ResolutionUnit -BitsPerSample -overwrite_original "{output_path}"'
        process = subprocess.Popen(
            cmd2, shell=True, creationflags=0x08000000, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8'
        )
        while process.poll() is None:
            progress_callback(75)
            QApplication.processEvents()
        result2 = subprocess.CompletedProcess(args=cmd2, returncode=process.returncode, stdout="", stderr="")
        return result2
    except Exception as e:
        return subprocess.CompletedProcess(args=cmd1 if 'cmd1' in locals() else "", returncode=1, stdout="", stderr=str(e))

conversion_functions = {
    "Video": {"MP4": convert_video_to_mp4, "MKV": convert_video_to_mkv, "WebM": convert_video_to_webm},
    "Audio": {"M4A": convert_audio_to_m4a, "FLAC": convert_audio_to_flac},
    "Image": {"ICO": convert_image_to_ico, "JPG": convert_image_to_jpg, "PNG": convert_image_to_png},
}

def is_valid_file(file_path, conversion_type):
    if not os.path.exists(file_path):
        return False
    ext = os.path.splitext(file_path)[1].lower()
    return ext in (
        video_extensions if conversion_type == "Video" else
        audio_extensions if conversion_type == "Audio" else
        image_extensions
    )

def get_output_file(input_file, extension):
    base_name = os.path.splitext(input_file)[0]
    output_file = f"{base_name}.{extension.lower()}"
    suffix = 1
    while os.path.exists(output_file):
        output_file = f"{base_name}_{suffix}.{extension.lower()}"
        suffix += 1
    return output_file

class ConversionThread(QThread):
    progress_signal = pyqtSignal(float)
    error_signal = pyqtSignal(str, dict)
    completed_signal = pyqtSignal(int, int)

    def __init__(self, files, conversion_type, selected_format, conversion_func, language):
        super().__init__()
        self.files = files
        self.conversion_type = conversion_type
        self.selected_format = selected_format
        self.conversion_func = conversion_func
        self.language = language
        self.process = None
        self.is_cancelled = False

    def stop(self):
        self.is_cancelled = True
        if self.process:
            try:
                process = psutil.Process(self.process.pid)
                for child in process.children(recursive=True):
                    try:
                        child.terminate()
                        child.wait(2)
                        if child.is_running():
                            child.kill()
                    except psutil.NoSuchProcess:
                        pass
                process.terminate()
                process.wait(2)
                if process.is_running():
                    process.kill()
                ffmpeg_processes.discard(self.process.pid)
            except psutil.NoSuchProcess:
                pass
            self.process = None
        terminate_ffmpeg_processes()
        cleanup_temp_files()

    def run(self):
        total_files = len(self.files)
        processed_files = 0
        failed_files = 0

        for input_file in self.files:
            if self.is_cancelled:
                break
            if not os.path.exists(input_file):
                failed_files += 1
                processed_files += 1
                self.error_signal.emit("file_access_error", {"file": input_file})
                self.progress_signal.emit((processed_files / total_files) * 100 if total_files > 0 else 100)
                continue

            output_file = get_output_file(input_file, self.selected_format)
            
            try:
                with open(input_file, 'rb') as f:
                    pass
                output_dir = os.path.dirname(output_file)
                if not os.access(output_dir, os.W_OK):
                    raise PermissionError(f"No write permission to directory: {output_dir}")
            except Exception as e:
                failed_files += 1
                processed_files += 1
                self.error_signal.emit("file_access_error", {"file": input_file})
                self.progress_signal.emit((processed_files / total_files) * 100 if total_files > 0 else 100)
                continue

            file_progress_start = (processed_files / total_files) * 100
            file_progress_end = ((processed_files + 1) / total_files) * 100

            try:
                def progress_callback(progress):
                    if self.is_cancelled:
                        return
                    file_progress = file_progress_start + (progress / 100) * (file_progress_end - file_progress_start)
                    self.progress_signal.emit(min(file_progress, 100))

                result = self.conversion_func(input_path=input_file, output_path=output_file, progress_callback=progress_callback)
                self.process = None
                if self.is_cancelled:
                    if os.path.exists(output_file):
                        try:
                            os.remove(output_file)
                        except Exception:
                            pass
                    break
                if result.returncode != 0:
                    failed_files += 1
                    self.error_signal.emit("conversion_error", {"file": input_file})
                    if os.path.exists(output_file):
                        try:
                            os.remove(output_file)
                        except Exception:
                            pass
                    processed_files += 1
                    self.progress_signal.emit(file_progress_end)
                elif not os.path.exists(output_file):
                    failed_files += 1
                    self.error_signal.emit("output_not_created", {"file": output_file})
                    if os.path.exists(output_file):
                        try:
                            os.remove(output_file)
                        except Exception:
                            pass
                    processed_files += 1
                    self.progress_signal.emit(file_progress_end)
                else:
                    processed_files += 1
                    self.progress_signal.emit(file_progress_end)
            except Exception as e:
                failed_files += 1
                self.error_signal.emit("conversion_error", {"file": input_file})
                if os.path.exists(output_file):
                    try:
                        os.remove(output_file)
                    except Exception:
                        pass
                processed_files += 1
                self.progress_signal.emit(file_progress_end)
            QApplication.processEvents()
        
        if self.is_cancelled:
            self.error_signal.emit("conversion_cancelled", {})
        elif failed_files != 0:
            if failed_files == total_files:
                self.error_signal.emit("conversion_failed", {"failed": failed_files, "total": total_files})
            else:
                self.error_signal.emit("completed_with_errors", {"failed": failed_files, "total": total_files})
        else:
            self.error_signal.emit("conversion_success", {})
        self.completed_signal.emit(failed_files, total_files)

class StartButton(QPushButton):
    def __init__(self, text, parent=None, language="en"):
        super().__init__(text, parent)
        self.language = language
        self.progress = 0
        self.completed = False
        self.cancelled = False
        self.is_converting = False
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.countdown_seconds = 0
        self.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                color: #ffffff;
                border: none;
                padding: 15px;
                border-radius: 5px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QPushButton:disabled {
                background-color: #3a3a3a;
                color: #aaaaaa;
            }
        """)
        self.setMinimumSize(200, 100)
        
    def format_time(self, seconds):
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds} {'сек' if self.language == 'ru' else 'sec'}"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes} {'м.' if self.language == 'ru' else 'min'} {secs} {'с.' if self.language == 'ru' else 'sec'}"
        elif seconds < 86400:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours} {'ч.' if self.language == 'ru' else 'hr'} {minutes} {'м.' if self.language == 'ru' else 'min'}"
        else:
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            return f"{days} {'д.' if self.language == 'ru' else 'days'} {hours} {'ч.' if self.language == 'ru' else 'hr'}"

    def set_progress(self, value):
        self.progress = min(max(value, 0), 100)
        self.completed = False
        self.cancelled = False
        self.countdown_timer.stop()
        self.setText(f"{int(self.progress)}%")
        self.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                color: #ffffff;
                border: none;
                padding: 15px;
                border-radius: 5px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QPushButton:disabled {
                background-color: #3a3a3a;
                color: #aaaaaa;
            }
        """)
        self.setIcon(QIcon())
        self.update()

    def set_completed(self, success=True):
        self.setEnabled(False)
        if success:
            self.completed = True
            self.cancelled = False
            self.progress = 100
            self.countdown_seconds = 3
            self.setText(f"✔ ({self.countdown_seconds} {'с.' if self.language == 'ru' else 'sec.'})")
            self.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: #ffffff;
                    border: none;
                    padding: 15px;
                    border-radius: 5px;
                    font-size: 16px;
                }
            """)
        else:
            self.completed = False
            self.cancelled = True
            self.countdown_seconds = 3
            self.setText(f"✖ ({self.countdown_seconds} {'с.' if self.language == 'ru' else 'sec.'})")
            self.setStyleSheet("""
                QPushButton {
                    background-color: #a83232;
                    color: #ffffff;
                    border: none;
                    padding: 15px;
                    border-radius: 5px;
                    font-size: 16px;
                }
            """)
        self.setIcon(QIcon())
        self.countdown_timer.start(1000)
        self.update()

    def set_cancelled(self):
        self.setEnabled(False)
        self.completed = False
        self.cancelled = True
        self.countdown_seconds = 3
        self.setText(f"✖ ({self.countdown_seconds} {'с.' if self.language == 'ru' else 'sec.'})")
        self.setStyleSheet("""
            QPushButton {
                background-color: #a83232;
                color: #ffffff;
                border: none;
                padding: 15px;
                border-radius: 5px;
                font-size: 16px;
            }
        """)
        self.setIcon(self.style().standardIcon(QStyle.SP_DialogCloseButton))
        self.countdown_timer.start(1000)
        self.update()

    def reset(self):
        if not self.is_converting:
            self.completed = False
            self.cancelled = False
            self.progress = 0
            self.countdown_timer.stop()
            self.setText(translations[self.language]["start"])
            self.setEnabled(True)
            self.setStyleSheet("""
                QPushButton {
                    background-color: #4a4a4a;
                    color: #ffffff;
                    border: none;
                    padding: 15px;
                    border-radius: 5px;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background-color: #5a5a5a;
                }
                QPushButton:disabled {
                    background-color: #3a3a3a;
                    color: #aaaaaa;
                }
            """)
            self.setIcon(QIcon())
            self.update()

    def update_countdown(self):
        self.countdown_seconds -= 1
        if self.countdown_seconds > 0:
            if self.completed:
                self.setText(f"✔ ({self.countdown_seconds} {'с.' if self.language == 'ru' else 'sec.'})")
            elif self.cancelled:
                self.setText(f"✖ ({self.countdown_seconds} {'с.' if self.language == 'ru' else 'sec.'})")
            self.update()
        else:
            self.countdown_timer.stop()
            self.reset()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.completed:
            painter.setBrush(QColor("#4CAF50"))
            painter.drawRoundedRect(self.rect(), 5, 5)
        elif self.cancelled:
            painter.setBrush(QColor("#a83232"))
            painter.drawRoundedRect(self.rect(), 5, 5)
        elif self.progress > 0:
            painter.setBrush(QColor("#4a4a4a"))
            painter.drawRoundedRect(self.rect(), 5, 5)
            painter.setBrush(QColor("#4CAF50"))
            painter.drawRoundedRect(0, 0, int(self.width() * self.progress / 100), self.height(), 5, 5)
        else:
            painter.setBrush(QColor("#4a4a4a"))
            painter.drawRoundedRect(self.rect(), 5, 5)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())

class MorphWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = configparser.ConfigParser()
        self.config_file = "settings.ini"
        self.language = "en"
        try:
            if os.path.exists(self.config_file):
                self.config.read(self.config_file, encoding="utf-8")
                self.language = self.config.get("Settings", "language", fallback="en")
        except Exception:
            pass

        try:
            if os.path.exists(self.config_file):
                self.config.read(self.config_file, encoding="utf-8")
                x = self.config.getint("Settings", "window_x", fallback=100)
                y = self.config.getint("Settings", "window_y", fallback=100)
                width = self.config.getint("Settings", "window_width", fallback=800)
                height = self.config.getint("Settings", "window_height", fallback=700)
                self.setGeometry(x, y, width, height)
            else:
                self.setGeometry(100, 100, 800, 700)
        except Exception:
            self.setGeometry(100, 100, 800, 700)
        
        self.setWindowTitle(translations[self.language]["window_title"])
        icon_path = None
        for ext in ["icon.png", "icon.ico"]:
            if os.path.exists(ext):
                icon_path = ext
                break
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))
            QApplication.setWindowIcon(QIcon(icon_path))
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; color: #ffffff; }
            QListWidget { background-color: #3c3c3c; color: #ffffff; border: none; }
            QPushButton { 
                background-color: #4a4a4a; 
                color: #ffffff; 
                border: none; 
                padding: 15px; 
                border-radius: 5px; 
                font-size: 16px; 
            }
            QPushButton:hover { background-color: #5a5a5a; }
            QStatusBar { background-color: #3c3c3c; color: #ffffff; }
            QTextEdit { background-color: #3c3c3c; color: #ffffff; border: none; }
            QMenu { background-color: #3c3c3c; color: #ffffff; }
            QMenu::item:selected { background-color: #5a5a5a; }
            QLabel { color: #999999; }
        """)
        self.setAcceptDrops(True)
        self.icon_provider = QFileIconProvider()

        self.taskbar_button = None
        if windows_taskbar_available and sys.platform == "win32":
            self.taskbar_button = QWinTaskbarButton(self)
            self.windowHandleCreated = False
            self.showEvent = self._showEvent

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        top_layout = QHBoxLayout()

        self.github_button = QPushButton("GitHub")
        self.github_button.setIcon(QIcon("github_logo.png"))
        self.github_button.clicked.connect(lambda: webbrowser.open("https://github.com/AlexanderNemchinov"))
        top_layout.addWidget(self.github_button)

        self.paypal_button = QPushButton("PayPal")
        self.paypal_button.setIcon(QIcon("paypal_logo.png"))
        self.paypal_button.clicked.connect(lambda: webbrowser.open("https://www.paypal.com/paypalme/AlexanderNemchinov"))
        top_layout.addWidget(self.paypal_button)

        self.donationalerts_button = QPushButton("DonationAlerts")
        self.donationalerts_button.setIcon(QIcon("donationalerts_logo.png"))
        self.donationalerts_button.clicked.connect(lambda: webbrowser.open("https://www.donationalerts.com/c/Nemchinov"))
        top_layout.addWidget(self.donationalerts_button)

        top_layout.addStretch()

        self.clear_all_button = QPushButton(translations[self.language]["clear_all"])
        self.clear_all_button.clicked.connect(self.clear_files)
        top_layout.addWidget(self.clear_all_button)

        self.language_button = QPushButton("EN" if self.language == "ru" else "RU")
        self.language_button.clicked.connect(self.toggle_language)
        top_layout.addWidget(self.language_button)

        main_layout.addLayout(top_layout)

        self.file_widget = QWidget()
        file_layout = QVBoxLayout()
        self.file_widget.setLayout(file_layout)
        self.file_list = QListWidget()
        self.file_list.setViewMode(QListWidget.IconMode)
        self.file_list.setIconSize(QSize(64, 64))
        self.file_list.setGridSize(QSize(100, 100))
        self.file_list.setResizeMode(QListWidget.Adjust)
        self.file_list.setMovement(QListWidget.Static)
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.show_context_menu)
        self.file_list.keyPressEvent = self.handle_key_press
        self.file_list.itemChanged.connect(self.update_drag_drop_label)
        self.file_list.itemChanged.connect(lambda: self.status_text.setText(""))
        file_layout.addWidget(self.file_list)

        self.drag_drop_label = QLabel(translations[self.language]["drag_drop"])
        self.drag_drop_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        self.drag_drop_label.setFont(font)
        effect = QGraphicsDropShadowEffect()
        effect.setColor(QColor("#000000"))
        effect.setOffset(2, 2)
        effect.setBlurRadius(10)
        self.drag_drop_label.setGraphicsEffect(effect)
        self.drag_drop_label.setStyleSheet("color: #999999;")
        self.drag_drop_label.setGeometry(0, 0, self.file_list.width(), self.file_list.height())
        self.drag_drop_label.setParent(self.file_list)
        self.file_list.resizeEvent = lambda event: self.drag_drop_label.setGeometry(0, 0, self.file_list.width(), self.file_list.height())
        main_layout.addWidget(self.file_widget)

        type_layout = QHBoxLayout()
        self.video_button = QPushButton(translations[self.language]["video"])
        self.audio_button = QPushButton(translations[self.language]["audio"])
        self.image_button = QPushButton(translations[self.language]["image"])
        for btn in (self.video_button, self.audio_button, self.image_button):
            btn.clicked.connect(lambda _, b=btn: self.select_type(b))
        type_layout.addWidget(self.video_button)
        type_layout.addWidget(self.audio_button)
        type_layout.addWidget(self.image_button)
        main_layout.addLayout(type_layout)

        self.format_start_layout = QHBoxLayout()
        self.format_layout = QVBoxLayout()
        self.format_start_layout.addLayout(self.format_layout)
        self.button_layout = QHBoxLayout()
        self.start_button = StartButton(translations[self.language]["start"], language=self.language)
        self.start_button.setVisible(False)
        self.start_button.clicked.connect(self.start_conversion)
        self.button_layout.addWidget(self.start_button, stretch=1)
        self.cancel_button = QPushButton(translations[self.language]["cancel"])
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_conversion)
        self.cancel_button.setStyleSheet(""" 
            QPushButton {
                background-color: #a83232;
                color: #ffffff;
                border: none;
                padding: 15px;
                border-radius: 5px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #c04040;
            }
        """)
        self.cancel_button.setMinimumSize(100, 100)
        self.button_layout.addWidget(self.cancel_button)
        self.format_start_layout.addLayout(self.button_layout)
        main_layout.addLayout(self.format_start_layout)

        self.status_bar = QStatusBar()
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setFixedHeight(60)
        self.status_text.setStyleSheet("background-color: #3c3c3c; color: #ffffff; border: none;")
        font = QFont()
        font.setPointSize(14)
        self.status_text.setFont(font)
        self.status_bar.addWidget(self.status_text, 1)
        self.setStatusBar(self.status_bar)

        self.conversion_type = None
        self.selected_format = None
        self.active_type_button = None
        self.active_format_button = None
        self.conversion_thread = None
        self.status_key = None
        self.status_params = None
        self.update_drag_drop_label()

    def _showEvent(self, event):
        super().showEvent(event)
        if windows_taskbar_available and sys.platform == "win32" and not self.windowHandleCreated:
            if self.windowHandle():
                self.taskbar_button.setWindow(self.windowHandle())
                self.windowHandleCreated = True

    def update_drag_drop_label(self):
        self.drag_drop_label.setVisible(self.file_list.count() == 0)
        self.drag_drop_label.setText(translations[self.language]["drag_drop"])

    def set_status_message(self, key, params):
        self.status_key = key
        self.status_params = params
        if key in translations[self.language]:
            try:
                message = translations[self.language][key].format(**params)
            except KeyError:
                message = translations[self.language][key]
        else:
            message = key
        self.status_text.setText(message)

    def toggle_language(self):
        old_language = self.language
        self.language = "en" if self.language == "ru" else "ru"
        self.start_button.language = self.language
        self.language_button.setText("EN" if self.language == "ru" else "RU")
        self.setWindowTitle(translations[self.language]["window_title"])
        self.clear_all_button.setText(translations[self.language]["clear_all"])
        self.video_button.setText(translations[self.language]["video"])
        self.audio_button.setText(translations[self.language]["audio"])
        self.image_button.setText(translations[self.language]["image"])
        self.cancel_button.setText(translations[self.language]["cancel"])
        if self.start_button.completed:
            self.start_button.setText(f"✔ ({self.start_button.countdown_seconds} {'с.' if self.language == 'ru' else 'sec.'})")
        elif self.start_button.cancelled:
            self.start_button.setText(f"✖ ({self.start_button.countdown_seconds} {'с.' if self.language == 'ru' else 'sec.'})")
        elif self.conversion_thread and self.conversion_thread.isRunning():
            self.start_button.setText(f"{int(self.start_button.progress)}%")
        else:
            self.start_button.reset()
        if self.status_key:
            self.set_status_message(self.status_key, self.status_params)
        if self.conversion_type and self.selected_format:
            formats = list(conversion_functions[self.conversion_type].keys())
            self.clear_format_layout()
            for fmt in formats:
                button = QPushButton(fmt)
                button.clicked.connect(lambda _, f=fmt: self.select_format(f))
                self.format_layout.addWidget(button)
                if fmt == self.selected_format:
                    self.active_format_button = button
                    effect = QGraphicsDropShadowEffect()
                    effect.setColor(QColor("#000000"))
                    effect.setOffset(2, 2)
                    effect.setBlurRadius(10)
                    button.setGraphicsEffect(effect)
                    button.setStyleSheet(""" 
                        QPushButton {
                            background-color: #4CAF50;
                            color: #ffffff;
                            border: none;
                            padding: 15px;
                            border-radius: 5px;
                            font-size: 16px;
                        }
                    """)
        self.update_drag_drop_label()
        try:
            if not self.config.has_section("Settings"):
                self.config.add_section("Settings")
            self.config.set("Settings", "language", self.language)
            with open(self.config_file, "w", encoding="utf-8") as configfile:
                self.config.write(configfile)
        except Exception:
            pass

    def handle_key_press(self, event):
        if event.key() == Qt.Key_Delete:
            self.remove_selected_files()
        else:
            QListWidget.keyPressEvent(self.file_list, event)

    def show_context_menu(self, position):
        menu = QMenu()
        clear_action = menu.addAction(translations[self.language]["clear"])
        clear_action.triggered.connect(self.remove_selected_files)
        menu.exec_(self.file_list.mapToGlobal(position))

    def remove_selected_files(self):
        selected_items = self.file_list.selectedItems()
        for item in selected_items:
            row = self.file_list.row(item)
            self.file_list.takeItem(row)
        self.status_text.setText("")
        self.status_key = None
        self.status_params = None
        self.update_drag_drop_label()

    def clear_files(self):
        self.file_list.clear()
        self.status_text.setText("")
        self.status_key = None
        self.status_params = None
        self.update_drag_drop_label()

    def select_type(self, button):
        if self.active_type_button:
            self.active_type_button.setStyleSheet(""" 
                QPushButton {
                    background-color: #4a4a4a;
                    color: #ffffff;
                    border: none;
                    padding: 15px;
                    border-radius: 5px;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background-color: #5a5a5a;
                }
            """)
            self.active_type_button.setGraphicsEffect(None)

        self.active_type_button = button
        effect = QGraphicsDropShadowEffect()
        effect.setColor(QColor("#000000"))
        effect.setOffset(2, 2)
        effect.setBlurRadius(10)
        button.setGraphicsEffect(effect)
        button.setStyleSheet(""" 
            QPushButton {
                background-color: #4CAF50;
                color: #ffffff;
                border: none;
                padding: 15px;
                border-radius: 5px;
                font-size: 16px;
            }
        """)

        self.conversion_type = {
            translations[self.language]["video"]: "Video",
            translations[self.language]["audio"]: "Audio",
            translations[self.language]["image"]: "Image"
        }[button.text()]
        self.clear_format_layout()
        self.start_button.setVisible(False)
        formats = list(conversion_functions[self.conversion_type].keys())
        self.show_format_buttons(formats)
        self.status_text.setText("")
        self.status_key = None
        self.status_params = None

    def show_format_buttons(self, formats):
        self.clear_format_layout()
        for fmt in formats:
            button = QPushButton(fmt)
            button.clicked.connect(lambda _, f=fmt: self.select_format(f))
            self.format_layout.addWidget(button)

    def clear_format_layout(self):
        while self.format_layout.count():
            item = self.format_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.active_format_button = None

    def select_format(self, fmt):
        if self.active_format_button:
            self.active_format_button.setStyleSheet(""" 
                QPushButton {
                    background-color: #4a4a4a;
                    color: #ffffff;
                    border: none;
                    padding: 15px;
                    border-radius: 5px;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background-color: #5a5a5a;
                }
            """)
            self.active_format_button.setGraphicsEffect(None)

        for i in range(self.format_layout.count()):
            button = self.format_layout.itemAt(i).widget()
            if button.text() == fmt:
                self.active_format_button = button
                effect = QGraphicsDropShadowEffect()
                effect.setColor(QColor("#000000"))
                effect.setOffset(2, 2)
                effect.setBlurRadius(10)
                button.setGraphicsEffect(effect)
                button.setStyleSheet(""" 
                    QPushButton {
                        background-color: #4CAF50;
                        color: #ffffff;
                        border: none;
                        padding: 15px;
                        border-radius: 5px;
                        font-size: 16px;
                    }
                """)
        self.selected_format = fmt
        self.start_button.setVisible(True)
        self.status_text.setText("")
        self.status_key = None
        self.status_params = None

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        for url in urls:
            path = url.toLocalFile()
            if os.path.exists(path):
                item = QListWidgetItem(os.path.basename(path))
                icon = generate_thumbnail(path)
                if not icon:
                    file_info = QFileInfo(path)
                    icon = self.icon_provider.icon(file_info)
                    if icon.isNull():
                        icon = QIcon("default_placeholder.png")
                item.setIcon(icon)
                item.setData(Qt.UserRole, path)
                self.file_list.addItem(item)
        self.status_text.setText("")
        self.status_key = None
        self.status_params = None
        self.update_drag_drop_label()

    def start_conversion(self):
        self.status_text.setText("")
        if not self.conversion_type or not self.selected_format:
            self.set_status_message("select_type_format", {})
            return
        if self.file_list.count() == 0:
            self.set_status_message("no_valid_files", {})
            return

        files_to_convert = []
        total_files = 0
        try:
            for i in range(self.file_list.count()):
                path = self.file_list.item(i).data(Qt.UserRole)
                if not os.path.exists(path):
                    continue
                if os.path.isdir(path):
                    valid_extensions = (
                        video_extensions if self.conversion_type == "Video" else
                        audio_extensions if self.conversion_type == "Audio" else
                        image_extensions
                    )
                    for root, _, files in os.walk(path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            if is_valid_file(file_path, self.conversion_type):
                                files_to_convert.append(file_path)
                                total_files += 1
                elif is_valid_file(path, self.conversion_type):
                    files_to_convert.append(path)
                    total_files += 1
        except Exception as e:
            self.set_status_message("collect_files_error", {"error": str(e)})
            return

        if total_files == 0:
            self.set_status_message("no_valid_files", {})
            return

        self.start_button.setEnabled(False)
        self.start_button.is_converting = True
        self.cancel_button.setVisible(True)
        conversion_func = conversion_functions[self.conversion_type][self.selected_format]
        
        self.conversion_thread = ConversionThread(files_to_convert, self.conversion_type, self.selected_format, conversion_func, self.language)
        self.conversion_thread.progress_signal.connect(self.update_progress)
        self.conversion_thread.error_signal.connect(self.set_status_message)
        self.conversion_thread.completed_signal.connect(self.handle_completion)
        self.conversion_thread.finished.connect(self.cleanup)
        self.conversion_thread.start()
        self.start_button.set_progress(0)
        if self.taskbar_button and self.windowHandleCreated:
            self.taskbar_button.progress().setVisible(True)
            self.taskbar_button.progress().setValue(0)

    def update_progress(self, value):
        self.start_button.set_progress(value)
        if self.taskbar_button and self.windowHandleCreated:
            self.taskbar_button.progress().setValue(int(value))

    def cancel_conversion(self):
        if self.conversion_thread and self.conversion_thread.isRunning():
            self.start_button.set_cancelled()
            self.set_status_message("conversion_cancelled", {})
            self.conversion_thread.stop()
            self.cancel_button.setVisible(False)
            if self.taskbar_button and self.windowHandleCreated:
                try:
                    self.taskbar_button.progress().setVisible(False)
                except Exception:
                    pass
            terminate_ffmpeg_processes()
            cleanup_temp_files()

    def handle_completion(self, failed_files, total_files):
        if self.conversion_thread.is_cancelled:
            self.start_button.set_cancelled()
        elif failed_files == 0:
            self.start_button.set_completed(success=True)
        else:
            self.start_button.set_completed(success=False)
        self.cancel_button.setVisible(False)
        if self.taskbar_button and self.windowHandleCreated:
            self.taskbar_button.progress().setVisible(False)
        cleanup_temp_files()
        terminate_ffmpeg_processes()

    def cleanup(self):
        self.conversion_thread = None
        self.start_button.is_converting = False
        if self.taskbar_button and self.windowHandleCreated:
            try:
                self.taskbar_button.progress().setVisible(False)
            except Exception:
                pass

    def closeEvent(self, event):
        if self.conversion_thread and self.conversion_thread.isRunning():
            self.conversion_thread.stop()
            self.conversion_thread.wait()
        if self.taskbar_button and self.windowHandleCreated:
            try:
                self.taskbar_button.progress().setVisible(False)
            except Exception:
                pass
        terminate_ffmpeg_processes()
        cleanup_temp_files(silent=True)
        try:
            if not self.config.has_section("Settings"):
                self.config.add_section("Settings")
            self.config.set("Settings", "window_x", str(self.x()))
            self.config.set("Settings", "window_y", str(self.y()))
            self.config.set("Settings", "window_width", str(self.width()))
            self.config.set("Settings", "window_height", str(self.height()))
            with open(self.config_file, "w", encoding="utf-8") as configfile:
                self.config.write(configfile)
        except Exception:
            pass
        event.accept()
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    icon_path = None
    for ext in ["icon.png", "icon.ico"]:
        if os.path.exists(ext):
            icon_path = ext
            break
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    window = MorphWindow()
    window.show()
    sys.exit(app.exec_())