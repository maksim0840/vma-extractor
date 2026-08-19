```
# В WSL Ubuntu
# 1. Скачиваем утилиту vma из репозитория Proxmox
wget http://download.proxmox.com/debian/pve/dists/bullseye/pve-no-subscription/binary-amd64/vma_1.1-2_amd64.deb

# 2. Устанавливаем пакет
sudo dpkg -i vma_1.1-2_amd64.deb

# 3. Если будут ошибки зависимостей
sudo apt-get install -f

# 4. Проверяем
vma --help
```
