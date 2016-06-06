#!/usr/bin/env ruby
#
# Given two Ruby simplecov output directories, show the differences
#

require 'json'

if ARGV.length != 2
  STDERR.puts "USAGE: ruby ruby_simplecov_diff.rb /path/to/old/dir /path/to/new/dir"
  exit 1
end

old_path = ARGV[0]
new_path = ARGV[1]

old_json = JSON.parse(File.read(File.join(old_path, '.resultset.json')))
new_json = JSON.parse(File.read(File.join(new_path, '.resultset.json')))
old_cov = old_json['RSpec']['coverage']
new_cov = new_json['RSpec']['coverage']

def get_line_percent(linearr)
  not_covered = 0
  linearr.each do |val|
    next if val.nil?
    not_covered += 1 if val < 1
  end
  return (((linearr.length - not_covered) * 1.0) / (linearr.length * 1.0)) * 100.0
end

def show_line_differences(old_linearr, new_linearr)
  old_pct = get_line_percent(old_linearr)
  new_pct = get_line_percent(new_linearr)
  if old_pct == new_pct
    return "coverage stayed the same"
  elsif old_pct < new_pct
    c = new_pct - old_pct
    return "coverage increased by #{c}%"
  else
    c = old_pct - new_pct
    return "coverage DECREASED by #{c}%"
  end
end

old_cov.each do |fpath, linearr|
  if ! new_cov.include?(fpath)
    puts "#{fpath} - missing in new"
    next
  end
  r = show_line_differences(linearr, new_cov[fpath])
  puts "#{fpath} - #{r}"
end
