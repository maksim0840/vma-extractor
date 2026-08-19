#!/usr/bin/env python3
"""
Скрипт для пакетной распаковки VMA/VMA.ZST файлов
Работает с утилитами zstd и vma
Временные файлы создаются в output директории
"""

import os
import sys
import subprocess
import time
import shutil
from pathlib import Path
from datetime import datetime
import argparse
import logging
import tempfile
from typing import List, Tuple, Optional

class VMAExtractor:
    def __init__(self, input_dir: str, output_dir: str, 
                 vma_path: str = "./vma", 
                 zstd_path: str = "/usr/bin/zstd",
                 keep_temp: bool = False,
                 log_file: str = None):
        """
        Инициализация экстрактора VMA.ZST файлов
        
        Args:
            input_dir: Путь к директории с VMA.ZST файлами
            output_dir: Путь к директории для результатов
            vma_path: Путь к утилите vma (по умолчанию ./vma)
            zstd_path: Путь к утилите zstd (по умолчанию /usr/bin/zstd)
            keep_temp: Сохранять временные .vma файлы
            log_file: Путь к файлу лога
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.vma_path = vma_path
        self.zstd_path = zstd_path
        self.keep_temp = keep_temp
        self.log_file = log_file
        self.temp_dir = None
        
        # Настройка логирования
        self.setup_logging()
        
        # Проверка наличия утилит
        self.check_tools()
    
    def setup_logging(self):
        """Настройка системы логирования"""
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        date_format = '%Y-%m-%d %H:%M:%S'
        
        self.logger = logging.getLogger('VMAExtractor')
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        
        # Консольный обработчик
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # Файловый обработчик (если указан)
        if self.log_file:
            file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(log_format, date_format)
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
    
    def check_tools(self):
        """Проверка наличия утилит"""
        # Проверка vma
        if not os.path.exists(self.vma_path) and not self._command_exists(self.vma_path):
            self.logger.error(f"❌ Утилита vma не найдена по пути: {self.vma_path}")
            self.logger.error("Укажите правильный путь через --vma-path")
            sys.exit(1)
        else:
            self.logger.info(f"✅ vma: {self.vma_path}")
        
        # Проверка zstd
        if not self._command_exists(self.zstd_path):
            self.logger.error(f"❌ Утилита zstd не найдена: {self.zstd_path}")
            self.logger.error("Установите zstd или укажите путь через --zstd-path")
            sys.exit(1)
        else:
            self.logger.info(f"✅ zstd: {self.zstd_path}")
    
    def _command_exists(self, command: str) -> bool:
        """Проверка существования команды"""
        try:
            if os.path.exists(command):
                result = subprocess.run([command, '--version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5)
            else:
                result = subprocess.run([command, '--version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5,
                                      shell=True)
            return result.returncode == 0
        except:
            return False
    
    def find_vma_files(self) -> List[Path]:
        """Поиск всех VMA.ZST и VMA файлов"""
        if not self.input_dir.exists():
            self.logger.error(f"❌ Директория {self.input_dir} не существует!")
            sys.exit(1)
        
        vma_files = []
        
        # Поиск различных расширений
        patterns = [
            "*.vma.zst", "*.VMA.ZST",
            "*.vma.zstd", "*.VMA.ZSTD",
            "*.vma", "*.VMA"
        ]
        
        for pattern in patterns:
            vma_files.extend(self.input_dir.glob(pattern))
        
        # Убираем дубликаты и сортируем
        vma_files = sorted(list(dict.fromkeys(vma_files)))
        
        if not vma_files:
            self.logger.error(f"❌ VMA файлы не найдены в {self.input_dir}")
            sys.exit(1)
        
        return vma_files
    
    def is_zst_compressed(self, file_path: Path) -> bool:
        """Проверка, является ли файл сжатым ZST"""
        return file_path.suffix.lower() in ['.zst', '.zstd']
    
    def decompress_zst(self, zst_file: Path, output_dir: Path) -> Optional[Path]:
        """
        Распаковка .vma.zst файла в output директорию
        
        Args:
            zst_file: Путь к .vma.zst файлу
            output_dir: Директория для распакованного .vma файла
            
        Returns:
            Path: путь к распакованному .vma файлу или None в случае ошибки
        """
        # Получаем имя файла без расширения .zst
        vma_name = zst_file.name
        if vma_name.lower().endswith('.zst'):
            vma_name = vma_name[:-4]
        elif vma_name.lower().endswith('.zstd'):
            vma_name = vma_name[:-5]
        
        # Создаем путь для распакованного файла в output директории
        temp_vma = output_dir / f".{vma_name}.tmp"  # Временный файл с точкой в начале
        
        self.logger.info(f"📦 Распаковка ZST: {zst_file.name}")
        self.logger.info(f"   Размер сжатого файла: {self.format_size(zst_file.stat().st_size)}")
        self.logger.info(f"   Временный файл: {temp_vma}")
        
        # Формируем команду как список (без shell=True)
        cmd = [self.zstd_path, str(zst_file), "-o", str(temp_vma)]
        
        self.logger.debug(f"Выполняю команду: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and temp_vma.exists():
                self.logger.info(f"✅ Распакован: {temp_vma.name}")
                self.logger.info(f"   Размер распакованного файла: {self.format_size(temp_vma.stat().st_size)}")
                return temp_vma
            else:
                self.logger.error(f"❌ Ошибка распаковки ZST")
                self.logger.error(f"   Команда: {' '.join(cmd)}")
                self.logger.error(f"   Код возврата: {result.returncode}")
                if result.stdout:
                    self.logger.error(f"   STDOUT: {result.stdout}")
                if result.stderr:
                    self.logger.error(f"   STDERR: {result.stderr}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Исключение при распаковке ZST: {e}")
            return None
    
    def extract_vma(self, vma_file: Path, output_dir: Path) -> bool:
        """
        Распаковка VMA файла
        
        Args:
            vma_file: Путь к .vma файлу
            output_dir: Директория для вывода (не должна существовать)
            
        Returns:
            bool: True если успешно
        """
        # Проверяем, что выходная директория не существует
        if output_dir.exists():
            self.logger.warning(f"⚠️  Директория {output_dir} уже существует")
            response = input(f"   Перезаписать? (y/N): ").lower().strip()
            if response == 'y':
                self.logger.info(f"   🗑️  Удаление существующей директории...")
                shutil.rmtree(output_dir)
            else:
                self.logger.info(f"   ⏭️  Пропуск")
                return False
        
        # Формируем команду как список
        cmd = [self.vma_path, "extract", "-v", str(vma_file), str(output_dir)]
        
        self.logger.debug(f"Выполняю команду: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                return True
            else:
                self.logger.error(f"  Ошибка VMA:")
                self.logger.error(f"  Команда: {' '.join(cmd)}")
                self.logger.error(f"  Код возврата: {result.returncode}")
                if result.stdout:
                    self.logger.error(f"  STDOUT: {result.stdout}")
                if result.stderr:
                    self.logger.error(f"  STDERR: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"  Исключение при распаковке VMA: {e}")
            return False
    
    def process_file(self, vma_file: Path, output_subdir: Path, parent_output: Path) -> bool:
        """
        Обработка одного файла (vma или vma.zst)
        
        Args:
            vma_file: Путь к файлу
            output_subdir: Директория для результатов VMA
            parent_output: Родительская output директория для временных файлов
            
        Returns:
            bool: True если успешно
        """
        temp_vma = None
        success = False
        
        try:
            if self.is_zst_compressed(vma_file):
                # Распаковываем ZST в output директорию
                temp_vma = self.decompress_zst(vma_file, parent_output)
                if not temp_vma:
                    return False
                file_to_extract = temp_vma
            else:
                # Обычный VMA файл
                file_to_extract = vma_file
            
            # Распаковываем VMA
            self.logger.info(f"🔄 Извлечение VMA: {file_to_extract.name}")
            success = self.extract_vma(file_to_extract, output_subdir)
            
            return success
            
        finally:
            # Очистка временных файлов
            if temp_vma and not self.keep_temp:
                try:
                    temp_vma.unlink()
                    self.logger.debug(f"Удален временный файл: {temp_vma}")
                except:
                    pass
            elif temp_vma and self.keep_temp:
                # Переименовываем временный файл в нормальное имя
                final_vma = parent_output / temp_vma.name.lstrip('.')
                try:
                    temp_vma.rename(final_vma)
                    self.logger.info(f"📁 Временный VMA сохранен: {final_vma.name}")
                except:
                    pass
    
    def extract_all(self):
        """Основной метод для распаковки всех файлов"""
        start_time = time.time()
        
        # Заголовок
        self.logger.info("=" * 70)
        self.logger.info("🔄 ПАКЕТНАЯ РАСПАКОВКА VMA/VMA.ZST ФАЙЛОВ")
        self.logger.info("=" * 70)
        self.logger.info(f"📁 Входная директория: {self.input_dir}")
        self.logger.info(f"📂 Выходная директория: {self.output_dir}")
        self.logger.info(f"🕐 Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 70)
        
        # Создаем выходную директорию
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Ищем файлы
        vma_files = self.find_vma_files()
        total_files = len(vma_files)
        
        # Статистика по типам файлов
        zst_files = [f for f in vma_files if self.is_zst_compressed(f)]
        regular_files = [f for f in vma_files if not self.is_zst_compressed(f)]
        
        self.logger.info(f"\n📋 Найдено файлов: {total_files}")
        if regular_files:
            self.logger.info(f"   📄 Обычные VMA: {len(regular_files)}")
        if zst_files:
            self.logger.info(f"   📦 Сжатые VMA.ZST: {len(zst_files)}")
        self.logger.info("")
        
        # Статистика выполнения
        successful = 0
        failed = 0
        failed_files = []
        
        # Обработка каждого файла
        for index, vma_file in enumerate(vma_files, 1):
            file_start_time = time.time()
            
            # Определяем имя выходной директории
            file_name = vma_file.name
            if self.is_zst_compressed(vma_file):
                # Убираем .zst расширение
                if file_name.lower().endswith('.zst'):
                    file_stem = file_name[:-4]
                else:
                    file_stem = file_name[:-5]
                # Убираем .vma расширение
                if file_stem.lower().endswith('.vma'):
                    file_stem = file_stem[:-4]
            else:
                file_stem = vma_file.stem
            
            output_subdir = self.output_dir / file_stem
            
            # Вывод информации
            self.logger.info(f"\n{'─' * 70}")
            self.logger.info(f"📦 Файл {index}/{total_files}: {file_name}")
            self.logger.info(f"   Тип: {'ZST сжатый' if self.is_zst_compressed(vma_file) else 'Обычный VMA'}")
            self.logger.info(f"   Размер: {self.format_size(vma_file.stat().st_size)}")
            self.logger.info(f"   Вывод в: {output_subdir}")
            progress_percent = index / total_files * 100
            progress_bar = '█' * int(40 * index / total_files) + '░' * (40 - int(40 * index / total_files))
            self.logger.info(f"   Прогресс: {progress_bar} {progress_percent:.1f}%")
            self.logger.info(f"{'─' * 70}")
            
            # Обработка файла
            if self.process_file(vma_file, output_subdir, self.output_dir):
                file_elapsed_time = time.time() - file_start_time
                successful += 1
                self.logger.info(f"✅ Успешно обработан: {file_name}")
                self.logger.info(f"   Время обработки: {file_elapsed_time:.2f} сек")
                if output_subdir.exists():
                    self.logger.info(f"   Размер результата: {self.get_directory_size(output_subdir)}")
            else:
                file_elapsed_time = time.time() - file_start_time
                failed += 1
                failed_files.append(file_name)
                self.logger.error(f"❌ Ошибка обработки: {file_name}")
                self.logger.error(f"   Время до ошибки: {file_elapsed_time:.2f} сек")
            
            # Промежуточная статистика
            self.logger.info(f"\n📊 Промежуточная статистика:")
            self.logger.info(f"   ✅ Успешно: {successful}")
            self.logger.info(f"   ❌ Ошибок: {failed}")
            self.logger.info(f"   ⏳ Осталось: {total_files - index}")
            
            # Оценка оставшегося времени
            if index > 0:
                elapsed_total = time.time() - start_time
                avg_time_per_file = elapsed_total / index
                remaining_files = total_files - index
                estimated_remaining = avg_time_per_file * remaining_files
                self.logger.info(f"   ⏱️  Примерное оставшееся время: {estimated_remaining/60:.1f} мин")
        
        # Финальная статистика
        total_time = time.time() - start_time
        self.logger.info(f"\n{'=' * 70}")
        self.logger.info("🏁 ЗАВЕРШЕНИЕ РАБОТЫ")
        self.logger.info(f"{'=' * 70}")
        self.logger.info(f"📊 ИТОГОВАЯ СТАТИСТИКА:")
        self.logger.info(f"   📦 Всего файлов: {total_files}")
        self.logger.info(f"   ✅ Успешно обработано: {successful}")
        self.logger.info(f"   ❌ Ошибок: {failed}")
        self.logger.info(f"   ⏱️  Общее время: {total_time/60:.1f} мин ({total_time:.2f} сек)")
        
        if failed_files:
            self.logger.info(f"\n❌ Файлы с ошибками:")
            for fname in failed_files:
                self.logger.info(f"   - {fname}")
        
        self.logger.info(f"📂 Результаты сохранены в: {self.output_dir}")
        self.logger.info(f"{'=' * 70}")
        
        return successful, failed
    
    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Форматирование размера в читаемый вид"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
    
    @staticmethod
    def get_directory_size(path: Path) -> str:
        """Получение размера директории"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                total_size += os.path.getsize(filepath)
        return VMAExtractor.format_size(total_size)


def main():
    parser = argparse.ArgumentParser(
        description='Пакетная распаковка VMA/VMA.ZST файлов',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Базовая обработка
  python3 vma_extractor.py -i /path/to/vma/files -o /path/to/output
  
  # С указанием путей к утилитам
  python3 vma_extractor.py -i /backup -o /restore --vma-path ./vma --zstd-path /usr/bin/zstd
  
  # С сохранением временных файлов
  python3 vma_extractor.py -i /backup -o /restore --keep-temp
  
  # С логированием
  python3 vma_extractor.py -i /backup -o /restore -l extract.log
        """
    )
    
    parser.add_argument('-i', '--input', required=True,
                       help='Путь к директории с VMA/VMA.ZST файлами')
    parser.add_argument('-o', '--output', required=True,
                       help='Путь к директории для результатов')
    parser.add_argument('--vma-path', default='./vma',
                       help='Путь к утилите vma (по умолчанию: ./vma)')
    parser.add_argument('--zstd-path', default='/usr/bin/zstd',
                       help='Путь к утилите zstd (по умолчанию: /usr/bin/zstd)')
    parser.add_argument('-l', '--log',
                       help='Путь к файлу лога')
    parser.add_argument('--keep-temp', action='store_true',
                       help='Сохранять временные .vma файлы')
    
    args = parser.parse_args()
    
    try:
        extractor = VMAExtractor(
            input_dir=args.input,
            output_dir=args.output,
            vma_path=args.vma_path,
            zstd_path=args.zstd_path,
            keep_temp=args.keep_temp,
            log_file=args.log
        )
        
        successful, failed = extractor.extract_all()
        
        sys.exit(0 if failed == 0 else 1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Процесс прерван пользователем!")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
