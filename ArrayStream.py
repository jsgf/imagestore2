from string import join

class ArrayStream:
    def __init__(self, data = []):
	self._data = data
	self.offset = 0

    def write(self, data):
	data = list(data)
	l = len(data)
	while len(self._data) < self.offset+l:
	    self._data.append(0)
	self._data[self.offset:(self.offset+l)] = data
	self.offset = self.offset + l

    def read(self, length=None):
	if length is None:
	    length = len(self._data) - self.offset
	elif length > len(self._data) - self.offset:
	    length = len(self._data) - self.offset

	ret = self._data[self.offset:self.offset+length]
	self.offset = self.offset+length
	return ret

    def seek(self, off, whence = 0):
	if whence == 1:
	    self.offset = self.offset + off
	elif whence == 2:
	    self.offset = len(self._data) + off
	else:
	    self.offset = off

    def data(self):
	return join(self._data, '')

