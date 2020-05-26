#!/usr/bin/env ruby

STDOUT.sync = true

require 'lastpass-api'
require 'io/console'
@lastpass = Lastpass::Client.new
Lastpass.verbose = true

raise("LastPass is NOT logged in! Please run 'lpass login' first!") unless @lastpass.logged_in?

print "Enter your OLD password: "
old_password = gets.chomp
print "Enter your NEW password: "
new_password = gets.chomp

puts "OLD Password: '#{old_password}' NEW password: '#{new_password}'"
puts 'Ctrl+C to exit, or Enter to continue...'
gets

@lastpass.accounts.find_all(with_passwords: true).each do |acct|
  next unless acct.password == old_password
  puts acct.to_h
  cmd = "printf 'Password: #{new_password}' | lpass edit --non-interactive --sync=no #{acct.id}"
  puts cmd
  Lastpass::Utils.cmd cmd
end
sleep 1 # Allow file IO before attempting sync
Lastpass::Utils.cmd 'lpass sync'
sleep 1 # Allow sync to finish
