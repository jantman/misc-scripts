# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.box = 'puppetlabs/centos-7.0-64-puppet'

  # Forward a port for the selenium instance
  config.vm.network "public_network"

  # Give the box a little more memory
  config.vm.provider "virtualbox" do |vb|
    vb.customize ["modifyvm", :id, "--memory", "2048"]
  end

  # Provision the machine with the appliction
  config.vm.provision "shell",
                      inline: "yum install -y rpm-build redhat-rpm-config make gcc openssl openssl-devel wget"
  config.vm.provision "shell",
                      inline: "mkdir -p /home/vagrant/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}"
  config.vm.provision "shell",
                      inline: "echo '%_topdir /home/vagrant/rpmbuild' > /home/vagrant/.rpmmacros"
  config.vm.provision "shell",
                      inline: "chown -R vagrant:vagrant /home/vagrant/.rpmmacros /home/vagrant/rpmbuild"
end
