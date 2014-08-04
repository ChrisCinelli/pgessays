pgessays
========

Paul Graham's essays from web to epub
This script crawl the web for Paul Graham's essays and compile them together in epub ebook that can be read on your laptop, tablet or phone.

The main file is `pgessays.py`. [The full collection of Paul Graham's essays is included on this repo](https://github.com/ChrisCinelli/pgessays/raw/master/Paul%20Graham's%20Essays.epub) (updated on August 4th, 2014).

### Run it

```
git clone git@github.com:ChrisCinelli/pgessays.git
cd pgessays
cd env
source bin/activate
cd ..
python pgessays.py
```
If you prefer to install your modules you can install them. Just check out branch `IWillDoIt`  with `git checkout IWillDoIt`.

Code comes from [this gist](https://gist.github.com/goc9000/4287475). 
I just unpacked and installed all what was necessary to make it run on **Ubuntu 12.04** and added a work around for a missing image that generated an exception.
