let count = 0, total = 0;
const q = name => document.querySelector(`[data-testid="${name}"]`);
for (const [name, price] of [['notebook',18],['pencil',12]]) q(`add-${name}`).addEventListener('click', () => {
  count++; total += price; q('cart-count').textContent = `${count} items`; q('cart-total').textContent = `Total: $${total.toFixed(2)}`;
});
q('search').addEventListener('input', e => {
  let visible=0;
  for(const name of ['notebook','pencil']) { const card=q(`${name}-card`); card.hidden=!card.textContent.toLowerCase().includes(e.target.value.toLowerCase()); if(!card.hidden) visible++; }
  q('search-empty').hidden=visible!==0;
});
q('apply-coupon').addEventListener('click', () => {
  q('coupon-message').textContent=q('coupon').value==='NOTES10' ? 'Discount applied: 10%' : 'Invalid discount code';
});
