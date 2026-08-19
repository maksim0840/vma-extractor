```
DIR=http://download.proxmox.com/debian/pve/dists/trixie/pve-no-subscription/binary-amd64

wget "$DIR/pve-qemu-kvm_11.0.3-2_amd64.deb"
wget "$DIR/libproxmox-backup-qemu0_2.0.2_amd64.deb"



mkdir -p tmp && dpkg -x pve-qemu-kvm_11.0.3-2_amd64.deb tmp
cp tmp/usr/bin/vma . && chmod +x vma && rm -rf tmp

sudo dpkg -i libproxmox-backup-qemu0_2.0.2_amd64.deb
ldd ./vma | grep 'not found'



sudo apt install -y libiscsi7 librbd1 libjemalloc2 libaio1t64 libslirp0 libnuma1



zstd -d vzdump-qemu-100-2026_08_19-12_00_00.vma.zst
./vma extract -v vzdump-qemu-100-2026_08_19-12_00_00.vma ./out
```
