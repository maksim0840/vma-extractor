#!/usr/bin/env python3
"""
Скрипт для пакетной распаковки VMA и VMA.ZST файлов
Поддерживает:
- .vma - обычные VMA файлы
- .vma.zst - сжатые Zstandard VMA файлы
- .VMA, .VMA.ZST - в верхнем регистре
"""

import os
import sys
import subprocess
import time
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
import argparse
import logging
from typing import List, Tuple, Optional

class VMAZstExtractor:
    def __init__(self, input_dir: str, output_dir: str, 
                 keep_temp: bool = False, log_file: str = None):
        """
        Инициализация экстрактора VMA/VMA.ZST файлов
        
        Args:
            input_dir: Путь к директории с VMA файлами
            output_dir: Путь к директории для результатов
            keep_temp: Сохранять временные распакованные .vma файлы
            log_file: Путь к файлу лога
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.keep_temp = keep_temp
        self.log_file = log_file
        self.temp_dir = None
        
        # Настройка логирования
        self.setup_logging()
        
        # Проверка наличия необходимых утилит
        self.check_required_tools()
    
    def setup_logging(self):
        """Настройка системы логирования"""
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        date_format = '%Y-%m-%d %H:%M:%S'
        
        self.logger = logging.getLogger('VMAZstExtractor')
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()
        
        # Консольный обработчик
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # Файловый обработчик
        if self.log_file:
            file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(log_format, date_format)
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
    
    def check_required_tools(self):
        """Проверка наличия необходимых утилит"""
        tools = {
            'vma': 'proxmox-ve',
            'zstd': 'zstd'
        }
        
        for tool, package in tools.items():
            try:
                result = subprocess.run([tool, '--version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5)
                if result.returncode != 0:
                    self.logger.error(f"❌ Утилита '{tool}' не работает!")
                    self.logger.error(f"Установите: apt install {package}")
                    sys.exit(1)
                else:
                    version = result.stdout.split('\n')[0] if result.stdout else 'unknown'
                    self.logger.info(f"✅ {tool}: {version}")
            except FileNotFoundError:
                self.logger.error(f"❌ Утилита '{tool}' не найдена!")
                self.logger.error(f"Установите: apt install {package}")
                sys.exit(1)
            except subprocess.TimeoutExpired:
                self.logger.error(f"❌ Утилита '{tool}' не отвечает")
                sys.exit(1)
    
    def find_vma_files(self) -> List[Path]:
        """Поиск всех VMA и VMA.ZST файлов"""
        if not self.input_dir.exists():
            self.logger.error(f"❌ Директория {self.input_dir} не существует!")
            sys.exit(1)
        
        vma_files = []
        
        # Поиск различных расширений
        patterns = [
            "*.vma", "*.VMA",
            "*.vma.zst", "*.VMA.ZST",
            "*.vma.zstd", "*.VMA.ZSTD"
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
    
    def decompress_zst(self, zst_file: Path) -> Optional[Path]:
        """
        Распаковка .vma.zst файла во временный .vma файл
        
        Returns:
            Path: путь к распакованному .vma файлу или None в случае ошибки
        """
        # Создаем временную директорию если ещё не создана
        if not self.temp_dir:
            self.temp_dir = Path(tempfile.mkdtemp(prefix='vma_temp_'))
            self.logger.debug(f"Создана временная директория: {self.temp_dir}")
        
        # Создаем путь для распакованного файла
        vma_name = zst_file.stem  # убираем .zst
        temp_vma = self.temp_dir / vma_name
        
        self.logger.info(f"📦 Распаковка ZST: {zst_file.name}...")
        self.logger.info(f"   Размер сжатого файла: {self.format_size(zst_file.stat().st_size)}")
        
        # Команда распаковки
        cmd = f"zstd -d {zst_file} -o {temp_vma} --force"
        
        try:
            # Запускаем распаковку с отображением прогресса
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Читаем вывод в реальном времени
            while True:
                output = process.stderr.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    # zstd выводит прогресс в stderr
                    self.logger.debug(f"  {output.strip()}")
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0 and temp_vma.exists():
                self.logger.info(f"✅ Распакован: {temp_vma.name}")
                self.logger.info(f"   Размер распакованного файла: {self.format_size(temp_vma.stat().st_size)}")
                return temp_vma
            else:
                self.logger.error(f"❌ Ошибка распаковки: {stderr}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Исключение при распаковке ZST: {e}")
            return None
    
    def extract_vma(self, vma_file: Path, output_subdir: Path) -> bool:
        """
        Распаковка VMA файла
        
        Args:
            vma_file: Путь к .vma файлу
            output_subdir: Директория для вывода
            
        Returns:
            bool: True если успешно
        """
        output_subdir.mkdir(parents=True, exist_ok=True)
        
        cmd = f"vma extract {vma_file} {output_subdir}"
        
        self.logger.debug(f"Выполнение: {cmd}")
        
        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Читаем вывод в реальном времени
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    self.logger.debug(f"  {output.strip()}")
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                return True
            else:
                if stderr:
                    self.logger.error(f"  Ошибка: {stderr.strip()}")
                return False
                
        except Exception as e:
            self.logger.error(f"  Исключение: {e}")
            return False
    
    def process_file(self, vma_file: Path, output_subdir: Path) -> bool:
        """
        Обработка одного файла (vma или vma.zst)
        
        Returns:
            bool: True если успешно
        """
        temp_vma = None
        success = False
        
        try:
            if self.is_zst_compressed(vma_file):
                # Распаковываем ZST
                temp_vma = self.decompress_zst(vma_file)
                if not temp_vma:
                    return False
                file_to_extract = temp_vma
            else:
                # Обычный VMA файл
                file_to_extract = vma_file
            
            # Распаковываем VMA
            self.logger.info(f"🔄 Извлечение VMA: {file_to_extract.name}...")
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
            
            # Определяем имя без всех расширений
            file_name = vma_file.name
            if self.is_zst_compressed(vma_file):
                # Для .vma.zst -> убираем оба расширения
                file_stem = vma_file.stem.replace('.vma', '').replace('.VMA', '')
                if not file_stem:  # если имя было backup.vma.zst
                    file_stem = vma_file.name.split('.')[0]
            else:
                file_stem = vma_file.stem
            
            output_subdir = self.output_dir / file_stem
            
            # Проверка существующей директории
            if output_subdir.exists() and any(output_subdir.iterdir()):
                self.logger.info(f"⚠️  Директория {output_subdir} уже существует")
                response = input(f"   Перезаписать? (y/N): ").lower().strip()
                if response != 'y':
                    self.logger.info(f"   ⏭️  Пропуск {file_name}")
                    continue
                else:
                    self.logger.info(f"   🗑️  Удаление существующей директории...")
                    shutil.rmtree(output_subdir)
            
            # Вывод информации
            self.logger.info(f"\n{'─' * 70}")
            self.logger.info(f"📦 Файл {index}/{total_files}: {file_name}")
            self.logger.info(f"   Тип: {'ZST сжатый' if self.is_zst_compressed(vma_file) else 'Обычный VMA'}")
            self.logger.info(f"   Размер: {self.format_size(vma_file.stat().st_size)}")
            self.logger.info(f"   Вывод в: {output_subdir}")
            self.logger.info(f"   Прогресс: {'█' * int(40 * index / total_files)}{'░' * (40 - int(40 * index / total_files))} {index/total_files*100:.1f}%")
            self.logger.info(f"{'─' * 70}")
            
            # Обработка файла
            if self.process_file(vma_file, output_subdir):
                file_elapsed_time = time.time() - file_start_time
                successful += 1
                self.logger.info(f"✅ Успешно обработан: {file_name}")
                self.logger.info(f"   Время обработки: {file_elapsed_time:.2f} сек")
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
        
        # Очистка временной директории
        if self.temp_dir and not self.keep_temp:
            try:
                shutil.rmtree(self.temp_dir)
                self.logger.debug(f"Удалена временная директория: {self.temp_dir}")
            except:
                pass
        elif self.temp_dir and self.keep_temp:
            self.logger.info(f"\n📁 Временные файлы сохранены в: {self.temp_dir}")
        
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


def main():
    parser = argparse.ArgumentParser(
        description='Пакетная распаковка VMA и VMA.ZST файлов',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Обработка всех VMA и VMA.ZST файлов
  python3 vma_zst_extractor.py -i /backup/vma -o /restore
  
  # С сохранением временных файлов
  python3 vma_zst_extractor.py -i /backup/vma -o /restore --keep-temp
  
  # С логированием
  python3 vma_zst_extractor.py -i /backup/vma -o /restore -l extract.log
        """
    )
    
    parser.add_argument('-i', '--input', required=True, 
                       help='Путь к директории с VMA/VMA.ZST файлами')
    parser.add_argument('-o', '--output', required=True,
                       help='Путь к директории для результатов')
    parser.add_argument('-l', '--log',
                       help='Путь к файлу лога')
    parser.add_argument('--keep-temp', action='store_true',
                       help='Сохранять временные распакованные .vma файлы')
    
    args = parser.parse_args()
    
    try:
        extractor = VMAZstExtractor(
            input_dir=args.input,
            output_dir=args.output,
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